"""Tally Prime XML export parser.

Tally exports data as XML using its proprietary ODBC/HTTP server or
the Data Exchange XML format (TallyXML).

Primary export: Voucher data from Tally's HTTP export
  Ledger → Vouchers → VoucherEntry

Usage:
  connector = TallyXMLConnector(config)
  # From file:
  result = connector.fetch(file_path="/path/to/tally_export.xml")
  # From Tally HTTP server (if running):
  result = connector.fetch(tally_host="localhost", tally_port=9000)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, List
try:
    import defusedxml.ElementTree as ET  # type: ignore[import-untyped]
except ImportError:
    from xml.etree import ElementTree as ET  # type: ignore[assignment]

from app.connectors.base import ConnectorConfig, ConnectorInterface, FetchResult
from app.models import NormalizedSpendLine

logger = logging.getLogger("opex.connector.tally_xml")

_TALLY_REQUEST_BODY = """<ENVELOPE>
  <HEADER><TALLYREQUEST>Export Data</TALLYREQUEST></HEADER>
  <BODY>
    <EXPORTDATA>
      <REQUESTDESC>
        <REPORTNAME>Voucher Register</REPORTNAME>
        <STATICVARIABLES>
          <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
        </STATICVARIABLES>
      </REQUESTDESC>
    </EXPORTDATA>
  </BODY>
</ENVELOPE>"""


class TallyXMLConnector(ConnectorInterface):
    """Tally Prime XML export → NormalizedSpendLine connector."""

    def authenticate(self) -> bool:
        creds = self._config.credentials
        if creds.get("tally_host"):
            try:
                import requests
                resp = requests.get(
                    f"http://{creds['tally_host']}:{creds.get('tally_port', 9000)}",
                    timeout=5,
                )
                return resp.status_code < 500
            except Exception:
                return False
        return True  # file-based always ok

    def fetch(self, **kwargs: Any) -> FetchResult:
        file_path = kwargs.get("file_path")
        tally_host = kwargs.get("tally_host") or self._config.credentials.get("tally_host")

        if file_path:
            return self._from_file(Path(str(file_path)))
        if tally_host:
            return self._from_http(
                tally_host,
                int(kwargs.get("tally_port") or self._config.credentials.get("tally_port") or 9000),
            )
        return FetchResult(errors=["Either file_path or tally_host required"], source_system_id=self.source_system_id)

    def _from_file(self, path: Path) -> FetchResult:
        if not path.exists():
            return FetchResult(errors=[f"File not found: {path}"], source_system_id=self.source_system_id)
        try:
            xml_text = path.read_text(encoding="utf-8-sig", errors="replace")
            lines = self._parse_xml(xml_text)
            logger.info('"tally_xml_fetch source=file rows=%d"', len(lines))
            return FetchResult(lines=lines, row_count=len(lines), source_system_id=self.source_system_id)
        except Exception as exc:
            return FetchResult(errors=[str(exc)], source_system_id=self.source_system_id)

    def _from_http(self, host: str, port: int) -> FetchResult:
        try:
            import requests
            resp = requests.post(
                f"http://{host}:{port}",
                data=_TALLY_REQUEST_BODY.encode("utf-8"),
                headers={"Content-Type": "text/xml"},
                timeout=30,
            )
            resp.raise_for_status()
            lines = self._parse_xml(resp.text)
            logger.info('"tally_xml_fetch source=http rows=%d"', len(lines))
            return FetchResult(lines=lines, row_count=len(lines), source_system_id=self.source_system_id)
        except Exception as exc:
            return FetchResult(errors=[str(exc)], source_system_id=self.source_system_id)

    def _parse_xml(self, xml_text: str) -> List[NormalizedSpendLine]:
        lines: List[NormalizedSpendLine] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            logger.error('"tally_xml_parse_error err=%s"', exc)
            return lines

        vouchers = root.findall(".//VOUCHER") or root.findall(".//TALLYMESSAGE/VOUCHER")
        for idx, v in enumerate(vouchers):
            try:
                vtype = (v.findtext("VOUCHERTYPENAME") or "").strip()
                if vtype.lower() not in ("payment", "purchase", "journal", "expense"):
                    continue
                party = (v.findtext("PARTYLEDGERNAME") or "").strip()
                date_raw = (v.findtext("DATE") or "").strip()
                # Tally date format: YYYYMMDD
                spend_date = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:8]}" if len(date_raw) == 8 else date_raw

                # Amount from AllLedgerEntries
                amount = 0.0
                for entry in v.findall(".//ALLLEDGERENTRIES.LIST") or v.findall(".//LEDGERENTRIES.LIST"):
                    dr = (entry.findtext("ISDEEMEDPOSITIVE") or "No").strip()
                    amt_text = (entry.findtext("AMOUNT") or "0").strip().replace("-", "")
                    if dr == "Yes":
                        amount += float(amt_text or 0)

                gl_code = str(v.findtext("LEDGERNAME") or "")
                voucher_no = str(v.findtext("VOUCHERNUMBER") or "")
                lines.append(NormalizedSpendLine(
                    row_id=idx,
                    supplier=party or gl_code or "Unknown",
                    description=f"{vtype} — {party}",
                    amount=amount,
                    category_id=gl_code or "tally_expense",
                    category_name=gl_code or "Tally Expense",
                    spend_date=spend_date,
                    currency="INR",
                    source_system_id=self.source_system_id,
                    source_record_id=voucher_no,
                ))
            except Exception as exc:
                logger.debug('"tally_xml_row_skip idx=%d err=%s"', idx, exc)
        return lines
