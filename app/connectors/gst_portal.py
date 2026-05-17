"""GSTR-2A / GSTR-2B CSV parser.

Downloaded from GSTN portal (https://www.gst.gov.in) or via GSP API.
Expected columns for GSTR-2A:
  GSTIN_of_supplier, Trade_Name, Invoice_number, Invoice_date, Invoice_value,
  Taxable_value, IGST, CGST, SGST, Cess, Place_of_supply, Reverse_charge

GSTR-2B has a similar schema; the connector handles both via column sniffing.

Usage:
  connector = GSTPortalConnector(config)
  result = connector.fetch(file_path="/path/to/gstr2a_202501.csv")
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, List, Optional

from app.connectors.base import ConnectorConfig, ConnectorInterface, FetchResult
from app.models import NormalizedSpendLine

logger = logging.getLogger("opex.connector.gst_portal")


class GSTPortalConnector(ConnectorInterface):
    """GSTR-2A/2B CSV → NormalizedSpendLine (gst_treatment=itc_eligible) connector."""

    def authenticate(self) -> bool:
        return True  # File-based

    def fetch(self, **kwargs: Any) -> FetchResult:
        file_path = Path(str(kwargs.get("file_path") or ""))
        if not file_path.exists():
            return FetchResult(errors=[f"File not found: {file_path}"], source_system_id=self.source_system_id)
        try:
            lines: List[NormalizedSpendLine] = []
            errors: List[str] = []
            with open(file_path, newline="", encoding="utf-8-sig") as fh:
                reader = csv.DictReader(fh)
                headers = {(h or "").lower().strip().replace(" ", "_") for h in (reader.fieldnames or [])}
                gstr_type = "2B" if "itc_availability" in headers else "2A"
                for idx, row in enumerate(reader):
                    try:
                        lines.append(self._map_row(row, idx, gstr_type))
                    except Exception as exc:
                        errors.append(f"row {idx}: {exc}")
            logger.info('"gst_portal_fetch type=%s rows=%d errors=%d"', gstr_type, len(lines), len(errors))
            return FetchResult(
                lines=lines, errors=errors, row_count=len(lines),
                source_system_id=self.source_system_id,
                metadata={"gstr_type": gstr_type},
            )
        except Exception as exc:
            logger.error('"gst_portal_fetch_error err=%s"', exc)
            return FetchResult(errors=[str(exc)], source_system_id=self.source_system_id)

    def _map_row(self, row: dict, idx: int, gstr_type: str) -> NormalizedSpendLine:
        norm = {k.lower().strip().replace(" ", "_"): v for k, v in row.items()}
        gstin = str(norm.get("gstin_of_supplier") or norm.get("supplier_gstin") or "")
        supplier = str(norm.get("trade_name") or norm.get("supplier_name") or gstin)
        taxable = float(norm.get("taxable_value") or 0.0)
        igst = float(norm.get("igst") or 0.0)
        cgst = float(norm.get("cgst") or 0.0)
        sgst = float(norm.get("sgst") or 0.0)
        total_tax = igst + cgst + sgst
        invoice_value = float(norm.get("invoice_value") or (taxable + total_tax))
        rc = str(norm.get("reverse_charge") or "N").upper()
        gst_treatment = "rcm" if rc == "Y" else "itc_eligible"
        return NormalizedSpendLine(
            row_id=idx,
            supplier=supplier,
            description=f"GSTR-{gstr_type} — {supplier}",
            amount=taxable,
            category_id="gst_input",
            category_name="GST Input Credit",
            vendor_gstin=gstin if gstin else None,
            gstin=gstin if gstin else None,
            gst_treatment=gst_treatment,
            currency="INR",
            spend_date=str(norm.get("invoice_date") or ""),
            source_system_id=self.source_system_id,
            source_record_id=str(norm.get("invoice_number") or ""),
        )
