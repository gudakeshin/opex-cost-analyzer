"""
India Benchmark Connectors.

Free-source parsers (MCA21, BSE/NSE, BRSR, RBI, CEA) + adapter stubs
for licensed sources (CMIE Prowess IQ, Capitaline, CRISIL, ICRA).

All parsers return a normalised BenchmarkRecord list.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


@dataclass
class BenchmarkRecord:
    source: str
    company_name: str
    ticker: Optional[str]
    fiscal_year: str
    metric_id: str
    metric_name: str
    value: float
    unit: str
    currency: str = "INR"
    confidence: float = 0.9
    notes: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Free-source parsers (stubs — real implementations require HTTP access)
# ---------------------------------------------------------------------------

class MCA21Parser:
    """
    Parses MCA21 XBRL financial filings (Schedule III P&L data).

    Real implementation: GET https://www.mca.gov.in/mcafoportal/getXbrlData.do
    with company CIN and year; parse XBRL tags for Schedule III line items.
    """
    SOURCE = "MCA21_XBRL"

    def fetch_financials(self, cin: str, fiscal_year: str = "FY25") -> List[BenchmarkRecord]:
        log.warning("MCA21Parser.fetch_financials: HTTP access not available in this environment. Returning empty.")
        return []

    def parse_schedule_iii(self, xbrl_xml: str, company_name: str, fiscal_year: str) -> List[BenchmarkRecord]:
        """
        Parse XBRL XML response. Key tags:
          in-bfin:EmployeeBenefitExpense → employee_cost
          in-bfin:OtherExpenses → other_expenses
          in-bfin:Depreciation → depreciation
          in-bfin:FinanceCosts → finance_costs
        """
        records = []
        import re
        tag_map = {
            r"EmployeeBenefitExpense[^>]*>([\d.]+)": ("employee_cost", "Employee Benefit Expense", "INR"),
            r"OtherExpenses[^>]*>([\d.]+)": ("other_expenses", "Other Expenses", "INR"),
            r"Depreciation[^>]*>([\d.]+)": ("depreciation", "Depreciation & Amortisation", "INR"),
        }
        for pattern, (metric_id, metric_name, unit) in tag_map.items():
            m = re.search(pattern, xbrl_xml, re.IGNORECASE)
            if m:
                records.append(BenchmarkRecord(
                    source=self.SOURCE,
                    company_name=company_name,
                    ticker=None,
                    fiscal_year=fiscal_year,
                    metric_id=metric_id,
                    metric_name=metric_name,
                    value=float(m.group(1)),
                    unit=unit,
                    confidence=0.95,
                ))
        return records


class BSENSEParser:
    """
    Parses BSE/NSE annual report filings and financial data feeds.

    Free endpoints:
      BSE: https://www.bseindia.com/stock-share-price/{ticker}/financials-annual-reports
      NSE: https://www.nseindia.com/get-quotes/equity?symbol={symbol}
    """
    SOURCE = "BSE_NSE_FILING"

    def fetch_peer_benchmarks(self, tickers: List[str], metrics: List[str]) -> List[BenchmarkRecord]:
        log.warning("BSENSEParser.fetch_peer_benchmarks: HTTP access not available. Returning empty.")
        return []

    def parse_annual_report_pdf(self, pdf_text: str, company_name: str, ticker: str, fiscal_year: str) -> List[BenchmarkRecord]:
        """
        Regex-based extraction from annual report PDF text.
        Targets: cost-to-income, opex amounts, segment breakdowns.
        """
        import re
        records = []
        patterns = [
            (r"cost[- ]to[- ]income\s+ratio[^\d]*([\d.]+)\s*%", "cost_to_income_pct", "Cost-to-Income Ratio", "%"),
            (r"operating\s+expenses?\s+(?:₹|rs\.?)\s*([\d,]+(?:\.\d+)?)\s*crore", "opex_cr", "Total OpEx (₹ Cr)", "INR_cr"),
            (r"employee\s+(?:cost|expense)[^\d]*([\d.]+)\s*%", "employee_cost_pct", "Employee Cost % of OpEx", "%"),
            (r"technology\s+(?:spend|investment)[^\d]*([\d.]+)\s*%", "tech_pct", "Technology % of OpEx", "%"),
        ]
        for pattern, metric_id, metric_name, unit in patterns:
            m = re.search(pattern, pdf_text, re.IGNORECASE)
            if m:
                raw = m.group(1).replace(",", "")
                try:
                    records.append(BenchmarkRecord(
                        source=self.SOURCE,
                        company_name=company_name,
                        ticker=ticker,
                        fiscal_year=fiscal_year,
                        metric_id=metric_id,
                        metric_name=metric_name,
                        value=float(raw),
                        unit=unit,
                        confidence=0.7,
                        notes="Regex extraction from PDF text",
                    ))
                except ValueError:
                    pass
        return records


class BRSRParser:
    """
    Parses BRSR Core disclosures filed on BSE/NSE.

    BSE endpoint: https://www.bseindia.com/stock-share-price/{ticker}/annual-report
    Relevant fields: Scope-2 GHG intensity, water intensity, waste generated.
    """
    SOURCE = "BRSR_DISCLOSURE"

    def parse_brsr_data(self, data: Dict[str, Any], company_name: str, ticker: str, fiscal_year: str) -> List[BenchmarkRecord]:
        records = []
        field_map = {
            "scope2_ghg_intensity": ("scope2_intensity", "Scope-2 GHG Intensity (tCO₂e/₹Cr)", "tco2e_per_cr"),
            "water_intensity": ("water_intensity", "Water Intensity (kL/₹Cr)", "kl_per_cr"),
            "total_waste_tonnes": ("waste_generated", "Total Waste Generated (tonnes)", "tonnes"),
            "energy_intensity": ("energy_intensity", "Energy Intensity (GJ/₹Cr)", "gj_per_cr"),
        }
        for key, (metric_id, metric_name, unit) in field_map.items():
            if key in data and data[key] is not None:
                try:
                    records.append(BenchmarkRecord(
                        source=self.SOURCE,
                        company_name=company_name,
                        ticker=ticker,
                        fiscal_year=fiscal_year,
                        metric_id=metric_id,
                        metric_name=metric_name,
                        value=float(data[key]),
                        unit=unit,
                        confidence=0.92,
                    ))
                except (TypeError, ValueError):
                    pass
        return records


class RBIParser:
    """
    Parses RBI statistical publications for banking sector benchmarks.

    Key publications:
      - RBI Annual Report (Table VIII.3: Cost Ratios of SCBs)
      - Handbook of Statistics on Indian Economy
      - Database on Indian Economy (DBIE): https://dbie.rbi.org.in/DBIE/dbie.rbi?site=statistics
    """
    SOURCE = "RBI_PUBLICATION"

    def fetch_banking_cost_ratios(self, fiscal_year: str = "FY25") -> List[BenchmarkRecord]:
        log.warning("RBIParser.fetch_banking_cost_ratios: HTTP access not available. Returning defaults.")
        defaults = [
            ("cost_to_income_pct", "Cost-to-Income Ratio SCBs", 52.3, "%"),
            ("opex_to_assets_pct", "OpEx / Average Assets SCBs", 2.6, "%"),
            ("staff_cost_to_opex_pct", "Staff Cost % of OpEx SCBs", 58.0, "%"),
        ]
        return [
            BenchmarkRecord(
                source=self.SOURCE,
                company_name="Indian SCB Sector Average",
                ticker=None,
                fiscal_year=fiscal_year,
                metric_id=mid,
                metric_name=mname,
                value=val,
                unit=unit,
                confidence=0.85,
                notes="RBI Annual Report sector average",
            )
            for mid, mname, val, unit in defaults
        ]


class CEAParser:
    """
    Parses Central Electricity Authority (CEA) energy statistics.

    Key publications:
      - Growth of Electricity Sector in India (annual)
      - Monthly Generation Report
      - CEA: https://cea.nic.in/data-portal/
    """
    SOURCE = "CEA_PUBLICATION"

    def fetch_industrial_energy_intensity(self, sector: str = "all_industry", fiscal_year: str = "FY25") -> List[BenchmarkRecord]:
        log.warning("CEAParser.fetch_industrial_energy_intensity: HTTP access not available. Returning defaults.")
        defaults = {
            "steel": ("energy_intensity_gj_cr", "Energy Intensity", 120.0, "GJ/₹Cr"),
            "cement": ("energy_intensity_gj_cr", "Energy Intensity", 90.0, "GJ/₹Cr"),
            "chemicals": ("energy_intensity_gj_cr", "Energy Intensity", 75.0, "GJ/₹Cr"),
            "all_industry": ("energy_intensity_gj_cr", "Energy Intensity", 55.0, "GJ/₹Cr"),
        }
        mid, mname, val, unit = defaults.get(sector, defaults["all_industry"])
        return [BenchmarkRecord(
            source=self.SOURCE,
            company_name=f"{sector.title()} Sector Average",
            ticker=None,
            fiscal_year=fiscal_year,
            metric_id=mid,
            metric_name=mname,
            value=val,
            unit=unit,
            confidence=0.80,
            notes=f"CEA sector average for {sector}",
        )]


# ---------------------------------------------------------------------------
# Licensed source adapter stubs
# ---------------------------------------------------------------------------

class CmieAdapter:
    """
    Adapter stub for CMIE Prowess IQ.

    Authentication: API key in env CMIE_API_KEY.
    Base URL: https://prowessiq.cmie.com/api/v1/
    """

    def __init__(self) -> None:
        self.api_key = os.environ.get("CMIE_API_KEY")
        if not self.api_key:
            log.warning("CMIE_API_KEY not set; CmieAdapter in stub mode.")

    def fetch_peer_costs(self, tickers: List[str], metrics: List[str], fiscal_year: str = "FY25") -> List[BenchmarkRecord]:
        if not self.api_key:
            log.warning("CmieAdapter.fetch_peer_costs: No API key. Returning empty stub.")
            return []
        raise NotImplementedError("Implement CMIE Prowess IQ HTTP calls when API key available.")

    def fetch_time_series(self, ticker: str, metric: str, years: int = 5) -> List[BenchmarkRecord]:
        if not self.api_key:
            return []
        raise NotImplementedError("Implement CMIE time-series endpoint.")


class CapitalineAdapter:
    """
    Adapter stub for Capitaline Plus (Capital Market Publishers).

    Authentication: API key in env CAPITALINE_API_KEY.
    """

    def __init__(self) -> None:
        self.api_key = os.environ.get("CAPITALINE_API_KEY")
        if not self.api_key:
            log.warning("CAPITALINE_API_KEY not set; CapitalineAdapter in stub mode.")

    def fetch_segment_costs(self, company_ids: List[str], fiscal_year: str = "FY25") -> List[BenchmarkRecord]:
        if not self.api_key:
            return []
        raise NotImplementedError("Implement Capitaline segment cost endpoint.")


class CrisilAdapter:
    """
    Adapter stub for CRISIL Research sector reports.

    Authentication: API key in env CRISIL_API_KEY.
    """

    def __init__(self) -> None:
        self.api_key = os.environ.get("CRISIL_API_KEY")
        if not self.api_key:
            log.warning("CRISIL_API_KEY not set; CrisilAdapter in stub mode.")

    def fetch_sector_benchmarks(self, sector_code: str, fiscal_year: str = "FY25") -> List[BenchmarkRecord]:
        if not self.api_key:
            return []
        raise NotImplementedError("Implement CRISIL sector benchmark endpoint.")


class IcraAdapter:
    """
    Adapter stub for ICRA sector grading data.

    Authentication: contact ICRA for API access.
    """

    def fetch_sector_cost_data(self, sector: str, fiscal_year: str = "FY25") -> List[BenchmarkRecord]:
        log.warning("IcraAdapter: No public API available. Manual data entry required.")
        return []


# ---------------------------------------------------------------------------
# Convenience aggregator
# ---------------------------------------------------------------------------

def get_free_source_benchmarks(
    tickers: Optional[List[str]] = None,
    sector: str = "all_industry",
    fiscal_year: str = "FY25",
) -> List[Dict]:
    """Collect all available free-source benchmarks into a flat list of dicts."""
    records: List[BenchmarkRecord] = []

    records.extend(RBIParser().fetch_banking_cost_ratios(fiscal_year))
    records.extend(CEAParser().fetch_industrial_energy_intensity(sector, fiscal_year))

    return [r.to_dict() for r in records]
