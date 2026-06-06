"""Source system connectors for OpEx Intelligence Platform.

Each connector implements ConnectorInterface (app/connectors/base.py).
All connectors normalize their output to List[NormalizedSpendLine].

Wired via ``POST /api/v1/connectors/{type}/ingest`` — see app/services/connector_ingest.py.
File-based connectors (Ariba CSV, HRMS CSV, Tally XML, MT940) ingest from files already
uploaded to the session directory. Remote connectors (SAP OData, GST portal) accept
``fetch_kwargs`` in the ingest request body.
"""
