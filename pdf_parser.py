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
    """
    Layout-agnostic block-based transaction parser.
    Works for:
    - Single-line structured tables (CommBank-like)
    - Multi-line wrapped blocks (Canara-like)
    """

    name = "generic_block_parser_v2"

    DATE_REGEX = re.compile(
        r"\b("
        r"\d{2}-\d{2}-\d{4}|"
        r"\d{2}/\d{2}/\d{4}|"
        r"\d{2}\s+[A-Za-z]{3,9}\s+\d{4}"
        r")\b"
    )

    MONEY_REGEX = re.compile(
        r"-?\$?\d{1,3}(?:,\d{3})*(?:\.\d{2})"
    )

    NOISE_KEYWORDS = [
        "transaction summary",
        "account number",
        "page ",
        "opening balance",
        "closing balance",
        "date particulars",
        "disclaimer",
        "created ",
    ]

    def detect_score(self, text: str, lines: List[str]) -> float:
        date_count = sum(1 for l in lines if self.DATE_REGEX.search(l))
        if date_count > 10:
            return 0.9
        if date_count > 3:
            return 0.6
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
                previous_balance = txn.balance

        return transactions

    # -------------------------
    # BLOCK BUILDER
    # -------------------------

    def _build_transaction_blocks(self, lines: List[str]) -> List[str]:
        blocks = []
        current_block = []

        for line in lines:
            if self.DATE_REGEX.search(line):
                if current_block:
                    blocks.append(" ".join(current_block))
                    current_block = []

            current_block.append(line)

        if current_block:
            blocks.append(" ".join(current_block))

        return blocks

    # -------------------------
    # BLOCK PARSER
    # -------------------------

    def _parse_block(
        self,
        block: str,
        previous_balance: Optional[float]
    ) -> Optional[ParsedTransaction]:

        date_match = self.DATE_REGEX.search(block)
        if not date_match:
            return None

        date_raw = date_match.group(0)
        date_val = self._try_parse_date(date_raw)
        if not date_val:
            return None

        money_matches = list(self.MONEY_REGEX.finditer(block))
        if not money_matches:
            return None

        # Last value = balance
        balance = self._to_float(money_matches[-1].group(0))

        # Second last (if exists) = transaction amount
        amount = None
        if len(money_matches) >= 2:
            amount = self._to_float(money_matches[-2].group(0))
        else:
            # fallback if only one amount found
            amount = self._to_float(money_matches[-1].group(0))

        if amount is None:
            return None

        description = block
        description = description.replace(date_raw, "").strip()

        # remove trailing balance & amount tokens from description
        description = description[: money_matches[-2].start()] if len(money_matches) >= 2 else description

        description = re.sub(r"\s+", " ", description).strip()

        transaction_type = self._infer_type(
            amount,
            balance,
            previous_balance
        )

        return ParsedTransaction(
            date=date_val,
            description=description,
            amount=abs(amount),
            transaction_type=transaction_type,
            balance=balance,
        )

    # -------------------------
    # HELPERS
    # -------------------------

    def _infer_type(
        self,
        amount: float,
        balance: Optional[float],
        previous_balance: Optional[float],
    ) -> str:

        # 1️⃣ If explicit negative
        if amount < 0:
            return "debit"

        # 2️⃣ If balance delta available
        if balance is not None and previous_balance is not None:
            if balance > previous_balance:
                return "credit"
            elif balance < previous_balance:
                return "debit"

        # 3️⃣ Fallback: assume positive = credit
        return "credit"

    def _to_float(self, token: str) -> Optional[float]:
        try:
            return float(token.replace("$", "").replace(",", ""))
        except:
            return None

    def _is_noise(self, line: str) -> bool:
        lower = line.lower()
        return any(k in lower for k in self.NOISE_KEYWORDS)

    def _try_parse_date(self, raw: str) -> Optional[datetime]:
        formats = [
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%d %b %Y",
            "%d %B %Y",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                continue
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
