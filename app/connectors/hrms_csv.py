"""Generic HRMS CSV connector (SuccessFactors, Darwinbox, Workday, Keka).

Normalizes payroll/headcount cost exports into NormalizedSpendLine.
Each HRMS has slightly different column names — this connector uses
column-name sniffing to handle the most common variants.

Expected columns (at least one of each group must be present):
  Supplier/Vendor: EmployeeName, Employee_Name, Name, LegalEntity
  Amount:          GrossSalary, Gross_Salary, CTC, Total_Cost, Amount
  CostCenter:      CostCenter, Cost_Center, Department, CC_Code
  Date:            PayrollDate, Payroll_Date, Month, Period
  GSTIN:           (optional) VendorGSTIN, GSTIN

Usage:
  connector = HRMSCSVConnector(config)
  result = connector.fetch(file_path="/path/to/hrms_payroll_202501.csv")
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, Dict, List

from app.connectors.base import ConnectorInterface, FetchResult
from app.models import NormalizedSpendLine

logger = logging.getLogger("opex.connector.hrms_csv")

# Column-name sniffing groups: (normalized_key, list_of_possible_raw_names)
_SNIFFER: List[tuple] = [
    ("supplier", ["employeename", "employee_name", "name", "employeeid", "empid", "legal_entity"]),
    ("amount", ["grosssalary", "gross_salary", "ctc", "total_cost", "amount", "totalcompensation", "payamount"]),
    ("cost_center_id", ["costcenter", "cost_center", "department", "cc_code", "dept", "businessunit", "bu_code"]),
    ("spend_date", ["payrolldate", "payroll_date", "month", "period", "paydate", "salarymonth"]),
    ("legal_entity_id", ["legalentity", "legal_entity", "company_code", "entity", "entityid"]),
    ("vendor_gstin", ["vendorgstin", "gstin", "gst_number"]),
    ("vendor_pan", ["pan", "pan_number", "vendorpan"]),
    ("vendor_msme_flag", ["msme", "msme_flag", "is_msme"]),
    ("source_record_id", ["employeeid", "empid", "payslipid", "recordid"]),
]


def _sniff_columns(headers: List[str]) -> Dict[str, str]:
    """Return mapping of normalized_key → actual_column_name."""
    norm_to_raw = {h.lower().replace(" ", "").replace("_", ""): h for h in headers}
    result: Dict[str, str] = {}
    for key, candidates in _SNIFFER:
        for c in candidates:
            raw = norm_to_raw.get(c.replace("_", ""))
            if raw:
                result[key] = raw
                break
    return result


class HRMSCSVConnector(ConnectorInterface):
    """Generic HRMS payroll CSV → NormalizedSpendLine connector."""

    def authenticate(self) -> bool:
        return True  # File-based

    def fetch(self, **kwargs: Any) -> FetchResult:
        file_path = Path(str(kwargs.get("file_path") or ""))
        if not file_path.exists():
            return FetchResult(errors=[f"File not found: {file_path}"], source_system_id=self.source_system_id)
        try:
            lines: List[NormalizedSpendLine] = []
            errors: List[str] = []
            col_map: Dict[str, str] = {}
            with open(file_path, newline="", encoding="utf-8-sig") as fh:
                reader = csv.DictReader(fh)
                col_map = _sniff_columns(list(reader.fieldnames or []))
                if "amount" not in col_map:
                    return FetchResult(
                        errors=["No amount column found; check HRMS export format"],
                        source_system_id=self.source_system_id,
                    )
                for idx, row in enumerate(reader):
                    try:
                        lines.append(self._map_row(row, idx, col_map))
                    except Exception as exc:
                        errors.append(f"row {idx}: {exc}")
            logger.info('"hrms_csv_fetch rows=%d errors=%d col_map=%s"', len(lines), len(errors), list(col_map.keys()))
            return FetchResult(lines=lines, errors=errors, row_count=len(lines), source_system_id=self.source_system_id)
        except Exception as exc:
            logger.error('"hrms_csv_fetch_error err=%s"', exc)
            return FetchResult(errors=[str(exc)], source_system_id=self.source_system_id)

    def _map_row(self, row: dict, idx: int, col_map: Dict[str, str]) -> NormalizedSpendLine:
        def get(key: str, default: str = "") -> str:
            col = col_map.get(key)
            return str(row.get(col, default) if col else default)

        amount_str = get("amount", "0").replace(",", "")
        amount = float(amount_str or 0.0)
        supplier = get("supplier") or f"Employee-{idx}"
        msme_raw = get("vendor_msme_flag", "").lower()
        msme_flag = True if msme_raw in ("yes", "y", "true", "1") else (False if msme_raw in ("no", "n", "false", "0") else None)

        return NormalizedSpendLine(
            row_id=idx,
            supplier=supplier,
            description=f"Payroll — {supplier}",
            amount=amount,
            category_id="hr_payroll",
            category_name="HR Payroll",
            cost_center_id=get("cost_center_id") or None,
            currency="INR",
            spend_date=get("spend_date"),
            legal_entity_id=get("legal_entity_id") or None,
            vendor_gstin=get("vendor_gstin") or None,
            vendor_pan=get("vendor_pan") or None,
            vendor_msme_flag=msme_flag,
            source_system_id=self.source_system_id,
            source_record_id=get("source_record_id") or str(idx),
            spend_type="opex",
            is_addressable=False,  # Payroll is not directly addressable via supplier negotiation
        )
