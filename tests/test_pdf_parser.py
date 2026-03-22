"""Tests for pdf_parser.py — amount/date parsing logic (no actual PDFs needed)."""
import pytest
from datetime import datetime

from pdf_parser import (
    parse_amount_flexible,
    parse_date_flexible,
    GenericStatementParser,
)

# ── amount parsing ────────────────────────────────────────────────────────────

class TestParseAmountFlexible:
    def test_simple_integer(self):
        assert parse_amount_flexible("100") == 100.0

    def test_us_decimal(self):
        assert parse_amount_flexible("1,234.56") == 1234.56

    def test_eu_decimal(self):
        assert parse_amount_flexible("1.234,56") == 1234.56

    def test_negative_with_minus(self):
        assert parse_amount_flexible("-50.00") == -50.0

    def test_negative_with_parens(self):
        assert parse_amount_flexible("(75.00)") == -75.0

    def test_currency_symbol_stripped(self):
        assert parse_amount_flexible("$25.00") == 25.0
        assert parse_amount_flexible("€50.00") == 50.0
        assert parse_amount_flexible("£100") == 100.0

    def test_empty_returns_none(self):
        assert parse_amount_flexible("") is None
        assert parse_amount_flexible(None) is None

    def test_non_numeric_returns_none(self):
        assert parse_amount_flexible("abc") is None


# ── date parsing ──────────────────────────────────────────────────────────────

class TestParseDateFlexible:
    def test_iso_format(self):
        dt = parse_date_flexible("2026-03-15")
        assert dt.year == 2026
        assert dt.month == 3
        assert dt.day == 15

    def test_australian_format(self):
        dt = parse_date_flexible("15/03/2026")
        assert dt is not None
        assert dt.year == 2026

    def test_month_name(self):
        dt = parse_date_flexible("15 Jan 2026")
        assert dt is not None
        assert dt.month == 1

    def test_us_format_month_first(self):
        dt = parse_date_flexible("Jan 15 2026")
        assert dt is not None
        assert dt.day == 15

    def test_invalid_returns_none(self):
        dt = parse_date_flexible("not a date")
        assert dt is None

    def test_empty_returns_none(self):
        assert parse_date_flexible("") is None


# ── GenericStatementParser ────────────────────────────────────────────────────

class TestGenericStatementParser:
    def setup_method(self):
        self.parser = GenericStatementParser()

    def test_parse_simple_line(self):
        lines = ["15/03/2026 Coffee Shop 12.50 987.30"]
        results = self.parser.parse(" ".join(lines), lines)
        assert len(results) >= 1
        assert results[0].amount > 0

    def test_parse_from_table_rows(self):
        rows = [
            ["15/03/2026", "Grocery Store", "45.00", "1200.00"],
            ["16/03/2026", "Salary", "2000.00", "3200.00"],
        ]
        results = self.parser.parse_from_table_rows(rows)
        assert len(results) == 2

    def test_noise_lines_filtered(self):
        lines = [
            "Statement of Account",
            "Account Number: 1234",
            "15/03/2026 Coffee 5.00 100.00",
        ]
        results = self.parser.parse(" ".join(lines), lines)
        # Noise lines should not produce transactions
        for r in results:
            assert r.description not in ("Statement of Account", "Account Number: 1234")

    def test_detect_score_low_for_empty(self):
        score = self.parser.detect_score("", [])
        assert score < 0.5

    def test_detect_score_high_with_many_dates(self):
        lines = [f"{i:02d}/03/2026 Transaction {i} 10.00" for i in range(1, 15)]
        score = self.parser.detect_score("\n".join(lines), lines)
        assert score >= 0.5
