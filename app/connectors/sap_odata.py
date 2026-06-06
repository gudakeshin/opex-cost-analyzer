"""SAP S/4HANA GL connector via OData API.

Fetches GL line items from SAP S/4HANA using the standard OData service:
  /sap/opu/odata/sap/API_JOURNALENTRYITEM_SRV

Required credentials (ConnectorConfig.credentials):
  - base_url: e.g. "https://your-sap-host:44300"
  - username / password  (basic auth)
  - client: SAP client number (default "100")

Optional kwargs for fetch():
  - fiscal_year: int (e.g. 2025)
  - company_code: str
  - gl_account_from / gl_account_to: GL range filter
  - top: int — OData $top limit (default 5000)
"""
from __future__ import annotations

import logging
from typing import Any

from app.connectors.base import ConnectorInterface, FetchResult
from app.models import NormalizedSpendLine

logger = logging.getLogger("opex.connector.sap_odata")

_ODATA_PATH = "/sap/opu/odata/sap/API_JOURNALENTRYITEM_SRV/A_JournalEntryItem"


class SAPODataConnector(ConnectorInterface):
    """SAP S/4HANA GL → NormalizedSpendLine connector."""

    def authenticate(self) -> bool:
        try:
            import requests
            creds = self._config.credentials
            resp = requests.get(
                creds["base_url"] + "/sap/opu/odata/sap/API_JOURNALENTRYITEM_SRV",
                auth=(creds.get("username", ""), creds.get("password", "")),
                params={"sap-client": creds.get("client", "100"), "$top": "1", "$format": "json"},
                timeout=10,
            )
            ok = resp.status_code == 200
            logger.info('"sap_odata_auth status=%d ok=%s"', resp.status_code, ok)
            return ok
        except Exception as exc:
            logger.warning('"sap_odata_auth_failed err=%s"', exc)
            return False

    def fetch(self, **kwargs: Any) -> FetchResult:
        try:
            import requests
            creds = self._config.credentials
            params: dict = {
                "sap-client": creds.get("client", "100"),
                "$format": "json",
                "$top": str(kwargs.get("top", 5000)),
            }
            filters = []
            if kwargs.get("fiscal_year"):
                filters.append(f"FiscalYear eq '{kwargs['fiscal_year']}'")
            if kwargs.get("company_code"):
                filters.append(f"CompanyCode eq '{kwargs['company_code']}'")
            if filters:
                params["$filter"] = " and ".join(filters)

            resp = requests.get(
                creds["base_url"] + _ODATA_PATH,
                auth=(creds.get("username", ""), creds.get("password", "")),
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            records = resp.json().get("d", {}).get("results", [])
            lines = [self._map_record(r, idx) for idx, r in enumerate(records)]
            logger.info('"sap_odata_fetch rows=%d"', len(lines))
            return FetchResult(lines=lines, row_count=len(lines), source_system_id=self.source_system_id)
        except Exception as exc:
            logger.error('"sap_odata_fetch_error err=%s"', exc)
            return FetchResult(errors=[str(exc)], source_system_id=self.source_system_id)

    def _map_record(self, r: dict, idx: int) -> NormalizedSpendLine:
        amount = float(r.get("AmountInCompanyCodeCurrency") or 0.0)
        return NormalizedSpendLine(
            row_id=idx,
            supplier=str(r.get("AssignmentReference") or r.get("DocumentItemText") or ""),
            description=str(r.get("DocumentItemText") or ""),
            amount=amount,
            category_id=str(r.get("GLAccount") or ""),
            category_name=str(r.get("GLAccountName") or r.get("GLAccount") or ""),
            gl_code=str(r.get("GLAccount") or ""),
            cost_center_id=str(r.get("CostCenter") or None),
            currency=str(r.get("CompanyCodeCurrency") or "INR"),
            fiscal_year=int(r.get("FiscalYear") or 0) or None,
            source_system_id=self.source_system_id,
            source_record_id=str(r.get("AccountingDocument") or ""),
            spend_date=str(r.get("PostingDate") or ""),
        )
