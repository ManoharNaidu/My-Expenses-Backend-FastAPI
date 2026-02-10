import pdfplumber
import re
from datetime import datetime
from dataclasses import dataclass
from typing import List


@dataclass
class ParsedTransaction:
    date: datetime
    description: str
    amount: float
    transaction_type: str
    balance: float


class TransactionPDFExtractor:
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path

    def extract(self) -> List[ParsedTransaction]:
        text = self._extract_text()
        return self._parse(text)

    def _extract_text(self) -> str:
        text = ""
        with pdfplumber.open(self.pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text

    def _parse(self, text: str) -> List[ParsedTransaction]:
        txns = []
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        current = None

        for line in lines:
            if self._is_noise(line):
                continue

            if self._is_start(line):
                if current:
                    txns.append(current)

                parts = line.split()
                date = datetime.strptime(" ".join(parts[:3]), "%d %b %Y")
                amount = self._amount(parts[-2])
                balance = self._amount(parts[-1])

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
