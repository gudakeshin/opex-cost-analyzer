"""SAP Ariba spend extract CSV parser.

Ariba exports a fixed-schema CSV from the Spend Analysis module.
Expected columns (mapped below; extras are silently ignored):
  InvoiceNumber, SupplierName, SupplierID, CommodityCode, CommodityDescription,
  InvoiceAmount, InvoiceCurrency, InvoiceDate, BuyingOrg, CostCenter,
  PaymentTerms, PurchaseOrder

Usage:
  connector = AribaCSVConnector(config)
  result = connector.fetch(file_path="/path/to/ariba_export.csv")
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, List

from app.connectors.base import ConnectorConfig, ConnectorInterface, FetchResult
from app.models import NormalizedSpendLine

logger = logging.getLogger("opex.connector.ariba_csv")

_COL_MAP = {
    "suppliername": "supplier",
    "invoiceamount": "amount",
    "invoicecurrency": "currency",
    "invoicedate": "spend_date",
    "invoicenumber": "source_record_id",
    "commoditydescription": "description",
    "commoditycode": "category_id",
    "costcenter": "cost_center_id",
    "paymentterms": "payment_terms_raw",
}


class AribaCSVConnector(ConnectorInterface):
    """SAP Ariba spend CSV → NormalizedSpendLine connector."""

    def authenticate(self) -> bool:
        # File-based: authentication is implicit via file access
        return True

    def fetch(self, **kwargs: Any) -> FetchResult:
        file_path = Path(str(kwargs.get("file_path") or ""))
        if not file_path.exists():
            return FetchResult(errors=[f"File not found: {file_path}"], source_system_id=self.source_system_id)
        try:
            lines: List[NormalizedSpendLine] = []
            errors: List[str] = []
            with open(file_path, newline="", encoding="utf-8-sig") as fh:
                reader = csv.DictReader(fh)
                for idx, row in enumerate(reader):
                    try:
                        lines.append(self._map_row(row, idx))
                    except Exception as exc:
                        errors.append(f"row {idx}: {exc}")
            logger.info('"ariba_csv_fetch rows=%d errors=%d"', len(lines), len(errors))
            return FetchResult(lines=lines, errors=errors, row_count=len(lines), source_system_id=self.source_system_id)
        except Exception as exc:
            logger.error('"ariba_csv_fetch_error err=%s"', exc)
            return FetchResult(errors=[str(exc)], source_system_id=self.source_system_id)

    def _map_row(self, row: dict, idx: int) -> NormalizedSpendLine:
        norm = {_COL_MAP.get(k.lower().replace(" ", ""), k): v for k, v in row.items()}
        amount = float(norm.get("amount") or 0.0)
        payment_raw = str(norm.get("payment_terms_raw") or "")
        payment_days = self._parse_payment_days(payment_raw)
        return NormalizedSpendLine(
            row_id=idx,
            supplier=str(norm.get("supplier") or ""),
            description=str(norm.get("description") or ""),
            amount=amount,
            category_id=str(norm.get("category_id") or ""),
            category_name=str(norm.get("description") or norm.get("category_id") or ""),
            cost_center_id=str(norm.get("cost_center_id") or None),
            currency=str(norm.get("currency") or "INR"),
            spend_date=str(norm.get("spend_date") or ""),
            source_system_id=self.source_system_id,
            source_record_id=str(norm.get("source_record_id") or ""),
            payment_terms_days=payment_days,
        )

    @staticmethod
    def _parse_payment_days(raw: str) -> int | None:
        import re
        m = re.search(r"(\d+)", raw)
        return int(m.group(1)) if m else None
