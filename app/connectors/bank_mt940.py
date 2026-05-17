"""SWIFT MT940 bank statement parser.

MT940 is the standard for electronic bank statements (SWIFT standard).
Each statement contains header blocks (1–4) and a transaction block (5)
with individual debit/credit lines tagged :61: and :86:.

Usage:
  connector = BankMT940Connector(config)
  result = connector.fetch(file_path="/path/to/statement.mt940")
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, List, Optional

from app.connectors.base import ConnectorConfig, ConnectorInterface, FetchResult
from app.models import NormalizedSpendLine

logger = logging.getLogger("opex.connector.bank_mt940")

# MT940 transaction line :61: pattern
# Format: :61:YYMMDD[MMDD]CRDAmount[N]Reference[//BankRef]
_T61_RE = re.compile(
    r":61:(\d{6})(\d{4})?"  # value date + entry date
    r"(C|D|RD|RC)"           # credit/debit indicator
    r"(\d+,\d+)"             # amount (European decimal comma)
    r"N?(\w+)"               # transaction reference
)
_T86_RE = re.compile(r":86:(.*?)(?=:6[012]:|$)", re.DOTALL)


class BankMT940Connector(ConnectorInterface):
    """SWIFT MT940 bank statement → NormalizedSpendLine connector."""

    def authenticate(self) -> bool:
        return True  # File-based

    def fetch(self, **kwargs: Any) -> FetchResult:
        file_path = Path(str(kwargs.get("file_path") or ""))
        if not file_path.exists():
            return FetchResult(errors=[f"File not found: {file_path}"], source_system_id=self.source_system_id)
        try:
            text = file_path.read_text(encoding="latin-1")
            lines = self._parse_mt940(text)
            logger.info('"bank_mt940_fetch rows=%d"', len(lines))
            return FetchResult(lines=lines, row_count=len(lines), source_system_id=self.source_system_id)
        except Exception as exc:
            logger.error('"bank_mt940_fetch_error err=%s"', exc)
            return FetchResult(errors=[str(exc)], source_system_id=self.source_system_id)

    def _parse_mt940(self, text: str) -> List[NormalizedSpendLine]:
        lines: List[NormalizedSpendLine] = []
        # Split into transactions at :61: tags
        # Pair each :61: with its following :86: description
        transactions = re.split(r"(?=:61:)", text)
        idx = 0
        for block in transactions:
            m61 = _T61_RE.search(block)
            if not m61:
                continue
            value_date_str = m61.group(1)  # YYMMDD
            dc = m61.group(3)  # C=credit, D=debit
            amount_str = m61.group(4).replace(",", ".")
            ref = m61.group(5)
            # Description from :86: tag
            m86 = _T86_RE.search(block)
            description = (m86.group(1) or "").strip().replace("\n", " ") if m86 else ref

            amount = float(amount_str)
            # Only ingest debits (outgoing payments) as spend
            if dc not in ("D", "RD"):
                continue

            # Parse YYMMDD → spend_date string
            try:
                yy, mm, dd = value_date_str[:2], value_date_str[2:4], value_date_str[4:6]
                year = 2000 + int(yy)
                spend_date = f"{year}-{mm}-{dd}"
            except Exception:
                spend_date = value_date_str

            lines.append(NormalizedSpendLine(
                row_id=idx,
                supplier=self._extract_supplier(description),
                description=description[:200],
                amount=amount,
                category_id="bank_debit",
                category_name="Bank Debit",
                currency="INR",
                spend_date=spend_date,
                source_system_id=self.source_system_id,
                source_record_id=ref,
            ))
            idx += 1
        return lines

    @staticmethod
    def _extract_supplier(description: str) -> str:
        """Best-effort supplier extraction from MT940 description text."""
        parts = description.split("/")
        for part in parts:
            part = part.strip()
            if len(part) > 3 and not part.isdigit():
                return part[:100]
        return description[:100]
