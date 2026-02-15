import pdfplumber
import re
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ParsedTransaction:
    date: datetime
    description: str
    amount: float
    transaction_type: str
    balance: Optional[float]


class BaseStatementParser:
    name: str = "base"

    def detect_score(self, text: str, lines: List[str]) -> float:
        raise NotImplementedError

    def parse(self, text: str, lines: List[str]) -> List[ParsedTransaction]:
        raise NotImplementedError


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


class GenericStatementParser(BaseStatementParser):
    name = "generic_statement_v1"

    _date_prefix = re.compile(
        r"^(?P<date>"
        r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
        r"\d{4}-\d{2}-\d{2}|"
        r"\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4}|"
        r"[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{2,4}"
        r")\s+(?P<rest>.+)$"
    )

    _amount_token = re.compile(
        r"\(?[-+]?[$€£¥₹]?\d[\d,]*(?:\.\d{1,2})?\)?(?:\s?(?:CR|DR|C|D))?",
        flags=re.IGNORECASE,
    )

    def detect_score(self, text: str, lines: List[str]) -> float:
        candidate_lines = 0
        for line in lines:
            if self._date_prefix.match(line):
                candidate_lines += 1
            if candidate_lines >= 3:
                break

        if candidate_lines >= 5:
            return 0.9
        if candidate_lines >= 3:
            return 0.7
        if candidate_lines >= 1:
            return 0.35
        return 0.0

    def parse(self, text: str, lines: List[str]) -> List[ParsedTransaction]:
        txns: List[ParsedTransaction] = []

        for line in lines:
            if self._is_noise(line):
                continue

            m = self._date_prefix.match(line)
            if not m:
                continue

            date_raw = m.group("date")
            rest = m.group("rest").strip()

            date_val = self._try_parse_date(date_raw)
            if not date_val:
                continue

            amount_matches = list(self._amount_token.finditer(rest))
            if not amount_matches:
                continue

            amount_match = amount_matches[-2] if len(amount_matches) >= 2 else amount_matches[-1]
            balance_match = amount_matches[-1] if len(amount_matches) >= 2 else None

            amount = self._parse_amount(amount_match.group(0))
            if amount is None:
                continue

            balance = self._parse_amount(balance_match.group(0)) if balance_match else None
            description = rest[: amount_match.start()].strip(" -\t")
            if not description:
                continue

            txns.append(
                ParsedTransaction(
                    date=date_val,
                    description=description,
                    amount=abs(amount),
                    transaction_type="credit" if amount > 0 else "debit",
                    balance=balance,
                )
            )

        return txns

    def _is_noise(self, line: str) -> bool:
        lower = line.lower()
        noise_terms = [
            "transaction summary",
            "statement period",
            "account number",
            "opening balance",
            "closing balance",
            "page ",
            "balance brought forward",
        ]
        return any(term in lower for term in noise_terms)

    def _try_parse_date(self, raw: str) -> Optional[datetime]:
        date_formats = [
            "%d %b %Y",
            "%d %B %Y",
            "%d/%m/%Y",
            "%d/%m/%y",
            "%m/%d/%Y",
            "%m/%d/%y",
            "%d-%m-%Y",
            "%d-%m-%y",
            "%Y-%m-%d",
            "%b %d %Y",
            "%B %d %Y",
            "%b %d, %Y",
            "%B %d, %Y",
        ]
        normalized = " ".join(raw.replace(",", ", ").split())

        for fmt in date_formats:
            try:
                return datetime.strptime(normalized, fmt)
            except ValueError:
                continue
        return None

    def _parse_amount(self, token: str) -> Optional[float]:
        if not token:
            return None

        t = token.strip().upper().replace(" ", "")
        is_negative = False

        if t.endswith("DR") or t.endswith("D"):
            is_negative = True
            t = re.sub(r"(DR|D)$", "", t)
        elif t.endswith("CR") or t.endswith("C"):
            t = re.sub(r"(CR|C)$", "", t)

        if t.startswith("(") and t.endswith(")"):
            is_negative = True
            t = t[1:-1]

        t = re.sub(r"[$€£¥₹,]", "", t)

        try:
            value = float(t)
            return -abs(value) if is_negative or value < 0 else abs(value)
        except ValueError:
            return None


class TransactionPDFExtractor:
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self._parsers: List[BaseStatementParser] = [
            CommBankStatementParser(),
            GenericStatementParser(),
        ]
        self.last_parser_name: Optional[str] = None

    def extract(self) -> List[ParsedTransaction]:
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
        best_parser: BaseStatementParser = self._parsers[-1]
        best_score = -1.0

        for parser in self._parsers:
            score = parser.detect_score(text, lines)
            if score > best_score:
                best_score = score
                best_parser = parser

        return best_parser
