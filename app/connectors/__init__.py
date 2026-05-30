"""Source system connectors for OpEx Intelligence Platform.

Each connector implements ConnectorInterface (app/connectors/base.py).
All connectors normalize their output to List[NormalizedSpendLine].

EXPERIMENTAL — NOT YET WIRED.
    These connectors (SAP OData, Ariba, Tally, MT940 bank, GST portal, HRMS) are
    fully implemented but are NOT yet routed through any ingestion endpoint or
    service. Today's ingestion path is file upload via app/services/ingestion.py.
    Planned wiring: a generic ``POST /connectors/{type}/ingest`` endpoint that runs
    the selected connector -> normalized lines -> run_core_pipeline. Until then,
    instantiate connectors directly only in scripts/tests.
"""
