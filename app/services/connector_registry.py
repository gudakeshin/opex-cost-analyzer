"""Registry of source-system connectors available for ingest."""
from __future__ import annotations

from typing import Any, Dict, Tuple, Type

from app.connectors.ariba_csv import AribaCSVConnector
from app.connectors.bank_mt940 import BankMT940Connector
from app.connectors.base import ConnectorConfig, ConnectorInterface
from app.connectors.gst_portal import GSTPortalConnector
from app.connectors.hrms_csv import HRMSCSVConnector
from app.connectors.sap_odata import SAPODataConnector
from app.connectors.tally_xml import TallyXMLConnector

ConnectorEntry = Tuple[Type[ConnectorInterface], str, str]

CONNECTOR_REGISTRY: Dict[str, ConnectorEntry] = {
    "ariba_csv": (AribaCSVConnector, "SAP Ariba CSV", "Ariba spend analysis CSV export"),
    "bank_mt940": (BankMT940Connector, "Bank MT940", "SWIFT MT940 bank statement file"),
    "gst_portal": (GSTPortalConnector, "GST Portal", "GSTR-2A / GST portal JSON export"),
    "hrms_csv": (HRMSCSVConnector, "HRMS CSV", "Payroll / headcount cost CSV (Darwinbox, Workday, etc.)"),
    "sap_odata": (SAPODataConnector, "SAP OData", "SAP OData spend extract"),
    "tally_xml": (TallyXMLConnector, "Tally XML", "Tally Prime voucher XML export"),
}


def list_connectors() -> list[Dict[str, str]]:
    return [
        {
            "type": key,
            "label": label,
            "description": desc,
        }
        for key, (_, label, desc) in sorted(CONNECTOR_REGISTRY.items())
    ]


def build_connector(
    connector_type: str,
    *,
    source_system_id: str | None = None,
    credentials: Dict[str, str] | None = None,
    extra: Dict[str, Any] | None = None,
) -> ConnectorInterface:
    entry = CONNECTOR_REGISTRY.get(connector_type)
    if not entry:
        raise KeyError(f"Unknown connector type: {connector_type}")
    cls, label, _ = entry
    config = ConnectorConfig(
        source_system_id=source_system_id or connector_type.upper(),
        source_system_name=label,
        credentials=credentials or {},
        extra=extra or {},
    )
    return cls(config)
