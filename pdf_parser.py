"""
Bank statement PDF parser — generalised for multiple banks and countries.

Supports:
- Date formats: DD/MM/YYYY, MM/DD/YYYY, YYYY-MM-DD, DD Mon YYYY, DD.MM.YYYY, etc.
- Amount formats: $ € £ ₹ (comma or dot decimals, thousands separators, parentheses for negative).
- Extraction: table-based (when PDF has a clear grid) and line/block-based (text).
"""

import pdfplumber
import re
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional, Tuple

# -----------------------------------------------------------------------------
# Parsed output
# -----------------------------------------------------------------------------


@dataclass
class ParsedTransaction:
    date: datetime
    description: str
    amount: float
    transaction_type: str  # "credit" | "debit"
    balance: Optional[float]


# -----------------------------------------------------------------------------
# International date parsing (multiple countries)
# -----------------------------------------------------------------------------

# Order matters: more specific patterns first to avoid partial matches.
DATE_PATTERNS = [
    (re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})\b"), None),   # 15 Jan 2024, 15 January 2024
    (re.compile(r"\b([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})\b"), None),  # Jan 15, 2024 (US)
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), None),                   # 2024-01-15 (ISO)
    (re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b"), None),      # 15-01-2024, 15/01/2024, 15.01.2024
    (re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2})\b"), None),      # 15-01-24 (2-digit year)
]

# (pattern, (day_idx, month_idx, year_idx)) for reordered groups; None = use strptime on full match.
DATE_REGEX_STRPTIME = [
    (re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})\b"), "%d %b %Y"),   # 15 Jan 2024
    (re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})\b"), "%d %B %Y"), # 15 January 2024
    (re.compile(r"\b([A-Za-z]{3})\s+(\d{1,2}),?\s+(\d{4})\b"), "%b %d %Y"),  # Jan 15, 2024
    (re.compile(r"\b([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})\b"), "%B %d %Y"),
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "%Y-%m-%d"),
    (re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b"), None),  # DD/MM/YYYY or MM/DD/YYYY — try both
    (re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2})\b"), None),  # 2-digit year
]

MONTH_NAMES = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def parse_date_flexible(raw: str) -> Optional[datetime]:
    """Parse a date string using international formats (AU, US, EU, ISO, etc.)."""
    raw = raw.strip()
    if not raw:
        return None

    # Try strptime-based patterns first (for named months).
    for pattern, fmt in DATE_REGEX_STRPTIME:
        m = pattern.search(raw)
        if not m:
            continue
        try:
            if fmt:
                return datetime.strptime(m.group(0), fmt)
            # DD/MM/YYYY or MM/DD/YYYY (numeric)
            g = m.groups()
            if len(g) == 3:
                a, b, y = int(g[0]), int(g[1]), int(g[2])
                if y < 100:
                    y += 2000 if y < 50 else 1900
                # Try (day, month) in both orders; use first valid.
                for (day, month) in ((a, b), (b, a)):
                    if 1 <= month <= 12 and 1 <= day <= 31:
                        try:
                            return datetime(y, month, day)
                        except ValueError:
                            continue
        except (ValueError, TypeError):
            continue

    # Fallback: any date-like token with named month
    for pattern, _ in DATE_PATTERNS:
        m = pattern.search(raw)
        if m:
            token = m.group(0)
            for fmt in ("%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y"):
                try:
                    return datetime.strptime(token.replace(".", "-").replace("/", "-"), fmt)
                except ValueError:
                    continue
    return None


def find_first_date(text: str) -> Optional[Tuple[re.Match, datetime]]:
    """Find first parseable date in text. Returns (match, datetime) or None."""
    for pattern, fmt in DATE_REGEX_STRPTIME:
        m = pattern.search(text)
        if not m:
            continue
        dt = parse_date_flexible(m.group(0))
        if dt:
            return (m, dt)
    for pattern, _ in DATE_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        dt = parse_date_flexible(m.group(0))
        if dt:
            return (m, dt)
    return None


# -----------------------------------------------------------------------------
# International amount parsing (multiple currencies and number formats)
# -----------------------------------------------------------------------------

# Currency symbols and abbreviations (space optional after).
CURRENCY_PREFIX = r"(?:[\$€£¥₹]\s*|USD\s*|EUR\s*|GBP\s*|AUD\s*|INR\s*|R\s|Rs\.?\s*|Fr\.?\s*|kr\.?\s*)?"

# Amount patterns: match full substring so we can parse with parse_amount_flexible.
# US/UK/AU: 1,234.56 or -100.00 or (100.00)
AMOUNT_US_STYLE = re.compile(
    r"(?:" + CURRENCY_PREFIX + r")?"
    r"[\(-]?\s*\d{1,3}(?:,\d{3})*(?:\.\d{2})?\s*[\)]?|"
    r"(?:" + CURRENCY_PREFIX + r")?"
    r"[\(-]?\s*\d+(?:\.\d{2})?\s*[\)]?"
)

# EU: 1.234,56 or 1 234,56
AMOUNT_EU_STYLE = re.compile(
    r"(?:" + CURRENCY_PREFIX + r")?"
    r"[\(]?\s*\d{1,3}(?:[.\s]\d{3})*,\d{2}\s*[\)]?|"
    r"(?:" + CURRENCY_PREFIX + r")?"
    r"[\(]?\s*\d+,\d{2}\s*[\)]?"
)

# Indian: 1,00,000.50
AMOUNT_INDIAN_STYLE = re.compile(
    r"(?:" + CURRENCY_PREFIX + r")?"
    r"[\(-]?\s*\d{1,2}(?:,\d{2})*(?:\.\d{2})?\s*[\)]?"
)


def parse_amount_flexible(token: str) -> Optional[float]:
    """
    Parse a single amount string from any common format.
    - Removes currency symbols and spaces.
    - Handles parentheses as negative: (100.00) -> -100.00
    - Handles comma decimal (EU): 1.234,56 -> 1234.56
    - Handles dot decimal (US/UK): 1,234.56 -> 1234.56
    """
    if not token or not token.strip():
        return None
    s = token.strip()
    negative = s.startswith("-") or (s.startswith("(") and ")" in s)
    s = s.replace("(", "").replace(")", "").replace("-", "").strip()
    # Remove currency symbols (check longer first)
    for sym in ["USD ", "EUR ", "GBP ", "AUD ", "INR ", "Rs. ", "Rs ", "Fr. ", "Fr ", "kr. ", "kr ", "$", "€", "£", "¥", "₹", "R "]:
        if s.upper().startswith(sym.upper()):
            s = s[len(sym):].strip()
            break
        if s.startswith(sym):
            s = s[len(sym):].strip()
            break
    # Normalise spaces (no spaces inside number)
    s = s.replace(" ", "")
    # Decide decimal format: which separator is the decimal point?
    if "," in s and "." in s:
        # One is thousands, one is decimal. Trailing ,XX = EU decimal; trailing .XX = US decimal.
        if re.search(r",\d{2}\s*$", s):
            s = s.replace(".", "").replace(",", ".")   # EU: 1.234,56
        else:
            s = s.replace(",", "")                      # US: 1,234.56
    elif "," in s:
        parts = s.split(",", 1)
        if len(parts) == 2 and len(parts[1]) == 2 and parts[1].isdigit():
            s = parts[0] + "." + parts[1]              # EU: 100,50
        else:
            s = s.replace(",", "")                      # US thousands
    try:
        val = float(s)
        return -val if negative else val
    except ValueError:
        return None


def find_all_amounts_in_text(text: str) -> List[Tuple[int, int, float]]:
    """
    Find all amount-like substrings in text. Returns list of (start, end, parsed_float).
    Tries US, EU, Indian patterns; deduplicates by span; merges overlapping.
    """
    seen_spans: set = set()
    results: List[Tuple[int, int, float]] = []

    def add(match):
        span = match.span()
        raw = match.group(0).strip()
        if not raw or span in seen_spans:
            return
        val = parse_amount_flexible(raw)
        if val is not None and abs(val) < 1e15:
            seen_spans.add(span)
            results.append((span[0], span[1], val))

    for m in AMOUNT_US_STYLE.finditer(text):
        add(m)
    for m in AMOUNT_EU_STYLE.finditer(text):
        add(m)
    for m in AMOUNT_INDIAN_STYLE.finditer(text):
        add(m)

    results.sort(key=lambda x: x[0])
    # Drop amounts whose span is fully inside another (prefer full e.g. 1,234.56 over 234.56)
    filtered = []
    for (start, end, val) in results:
        if any(s <= start and end <= e and (s, e) != (start, end) for (s, e, _) in results):
            continue
        filtered.append((start, end, val))
    return filtered


# -----------------------------------------------------------------------------
# Base parser interface
# -----------------------------------------------------------------------------


class BaseStatementParser:
    name: str = "base"

    def detect_score(self, text: str, lines: List[str]) -> float:
        raise NotImplementedError

    def parse(self, text: str, lines: List[str]) -> List[ParsedTransaction]:
        raise NotImplementedError


# -----------------------------------------------------------------------------
# CommBank-specific (Australia) — high score when detected
# -----------------------------------------------------------------------------


class CommBankStatementParser(BaseStatementParser):
    name = "commbank_v1"

    def detect_score(self, text: str, lines: List[str]) -> float:
        score = 0.0
        lower = text.lower()
        if "commbank" in lower:
            score += 0.65
        if "transaction summary" in lower:
            score += 0.2
        if any(re.match(r"\d{2} [A-Za-z]{3} \d{4}", line) for line in lines):
            score += 0.15
        return min(score, 1.0)

    def parse(self, text: str, lines: List[str]) -> List[ParsedTransaction]:
        txns: List[ParsedTransaction] = []
        current: Optional[ParsedTransaction] = None

        for line in lines:
            if self._is_noise(line):
                continue

            if self._is_start(line):
                if current:
                    txns.append(current)

                parts = line.split()
                if len(parts) < 6:
                    continue

                try:
                    date = datetime.strptime(" ".join(parts[:3]), "%d %b %Y")
                    amount = self._amount(parts[-2])
                    balance = self._amount(parts[-1])
                except Exception:
                    continue

                current = ParsedTransaction(
                    date=date,
                    description=" ".join(parts[3:-2]),
                    amount=abs(amount),
                    transaction_type="credit" if amount > 0 else "debit",
                    balance=balance,
                )
                continue

            if current and not line.startswith(("Value Date", "Card xx")):
                current.description += " " + line

        if current:
            txns.append(current)

        return txns

    def _is_start(self, line: str) -> bool:
        return bool(re.match(r"\d{2} [A-Za-z]{3} \d{4}", line))

    def _amount(self, value: str) -> float:
        return float(value.replace("$", "").replace(",", ""))

    def _is_noise(self, line: str) -> bool:
        return any(
            k in line
            for k in [
                "Transaction Summary",
                "Account Number",
                "Page ",
                "CommBank",
            ]
        )


# -----------------------------------------------------------------------------
# Generic statement parser (any bank / country)
# -----------------------------------------------------------------------------

NOISE_KEYWORDS = [
    "transaction summary", "account number", "page ", "opening balance",
    "closing balance", "date particulars", "disclaimer", "created ",
    "statement of account", "bank statement", "account statement",
    "balance brought forward", "balance carried forward", "credit debit",
    "value date", "transaction date", "reference", "footer", "confidential",
    "please refer", "terms and conditions", "page of ", "generated on",
    "auszug", "kontoauszug", "relevé", "estrato", "extracto", "saldo",
    "datum beschreibung", "date description", "s.no", "sr no",
]


class GenericStatementParser(BaseStatementParser):
    """
    Layout-agnostic parser for bank statements from any country.
    Supports multiple date and amount formats; works on line/block text and
    optionally on pre-extracted table rows.
    """

    name = "generic_international_v1"

    def detect_score(self, text: str, lines: List[str]) -> float:
        date_count = sum(1 for line in lines if find_first_date(line))
        if date_count > 10:
            return 0.7
        if date_count > 3:
            return 0.5
        return 0.2

    def parse(self, text: str, lines: List[str]) -> List[ParsedTransaction]:
        lines = [l.strip() for l in lines if l.strip()]
        lines = [l for l in lines if not self._is_noise(l)]

        transaction_blocks = self._build_transaction_blocks(lines)
        transactions: List[ParsedTransaction] = []
        previous_balance: Optional[float] = None

        for block in transaction_blocks:
            txn = self._parse_block(block, previous_balance)
            if txn:
                transactions.append(txn)
                if txn.balance is not None:
                    previous_balance = txn.balance

        return transactions

    def parse_from_table_rows(self, rows: List[List[str]]) -> List[ParsedTransaction]:
        """Parse when data is already in table form (e.g. from PDF table extraction)."""
        results: List[ParsedTransaction] = []
        for row in rows:
            if not row:
                continue
            row_text = " ".join(str(c) for c in row if c)
            txn = self._parse_block(row_text, None)
            if txn:
                results.append(txn)
        return results

    def _build_transaction_blocks(self, lines: List[str]) -> List[str]:
        blocks = []
        current_block = []

        for line in lines:
            if find_first_date(line):
                if current_block:
                    blocks.append(" ".join(current_block))
                    current_block = []
            current_block.append(line)

        if current_block:
            blocks.append(" ".join(current_block))
        return blocks

    def _parse_block(self, block: str, previous_balance: Optional[float]) -> Optional[ParsedTransaction]:
        date_info = find_first_date(block)
        if not date_info:
            return None
        _, date_val = date_info
        date_raw = date_info[0].group(0)

        amounts = find_all_amounts_in_text(block)
        if not amounts:
            return None

        # Last amount in block is often balance; second-last (or only) is transaction amount.
        balance = amounts[-1][2] if amounts else None
        if len(amounts) >= 2:
            amount = amounts[-2][2]
        else:
            amount = amounts[-1][2]

        # Description: remove date then all amount substrings (reverse order to keep indices)
        description = block.replace(date_raw, "", 1)
        for (start, end, _) in sorted(amounts, key=lambda x: -x[0]):
            if start < len(description):
                end = min(end, len(description))
                description = description[:start] + " " + description[end:]
        description = re.sub(r"\s+", " ", description).strip()
        if len(description) > 500:
            description = description[:500]

        transaction_type = self._infer_type(amount, balance, previous_balance)

        return ParsedTransaction(
            date=date_val,
            description=description or "Transaction",
            amount=abs(amount),
            transaction_type=transaction_type,
            balance=balance,
        )

    def _infer_type(
        self,
        amount: float,
        balance: Optional[float],
        previous_balance: Optional[float],
    ) -> str:
        if amount < 0:
            return "debit"
        if balance is not None and previous_balance is not None:
            if balance > previous_balance:
                return "credit"
            if balance < previous_balance:
                return "debit"
        return "credit"

    def _is_noise(self, line: str) -> bool:
        lower = line.lower()
        return any(k in lower for k in NOISE_KEYWORDS)


# -----------------------------------------------------------------------------
# Table-based extraction (for PDFs that are clearly tabular)
# -----------------------------------------------------------------------------


def extract_transactions_from_tables(pdf_path: str, generic_parser: GenericStatementParser) -> List[ParsedTransaction]:
    """
    Try to extract transaction rows from PDF tables (e.g. many EU/US bank statements).
    Returns empty list if no suitable table is found.
    """
    all_rows: List[List[str]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables or []:
                if not table:
                    continue
                # Skip header-only or too few columns
                if len(table) < 2:
                    continue
                first_row = table[0]
                num_cols = len(first_row) if first_row else 0
                if num_cols < 2:
                    continue
                # Heuristic: at least one cell in first data row looks like a date or number
                for row in table[1:]:
                    if not row:
                        continue
                    row_clean = [str(c).strip() if c else "" for c in row]
                    if not any(row_clean):
                        continue
                    # Require at least one number-like cell (amount or date digits)
                    if any(re.search(r"\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d+[,.]\d{2}|\d{4}-\d{2}-\d{2}", str(c)) for c in row_clean if c):
                        all_rows.append(row_clean)

    if not all_rows:
        return []
    return generic_parser.parse_from_table_rows(all_rows)


# -----------------------------------------------------------------------------
# Main extractor: table-first, then text with best-matching parser
# -----------------------------------------------------------------------------


class TransactionPDFExtractor:
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self._parsers: List[BaseStatementParser] = [
            CommBankStatementParser(),
            GenericStatementParser(),
        ]
        self.last_parser_name: Optional[str] = None

    def extract(self) -> List[ParsedTransaction]:
        # 1) Try table-based extraction first (works for many modern bank PDFs).
        generic = GenericStatementParser()
        table_txns = extract_transactions_from_tables(self.pdf_path, generic)
        if table_txns:
            self.last_parser_name = "generic_table_v1"
            return table_txns

        # 2) Fall back to text-based extraction and parser selection.
        text = self._extract_text()
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        parser = self._select_parser(text, lines)
        self.last_parser_name = parser.name
        return parser.parse(text, lines)

    def _extract_text(self) -> str:
        text = ""
        with pdfplumber.open(self.pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text

    def _select_parser(self, text: str, lines: List[str]) -> BaseStatementParser:
        best_parser = self._parsers[-1]
        best_score = -1.0
        for parser in self._parsers:
            score = parser.detect_score(text, lines)
            if score > best_score:
                best_score = score
                best_parser = parser
        return best_parser
