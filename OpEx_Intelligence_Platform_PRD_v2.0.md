# OpEx Intelligence Platform — Product Requirements Document v2.0

**A Consultant-Deployable Cost Diagnostic Asset for Indian Enterprises**

| Field            | Detail                                                                 |
| ---------------- | ---------------------------------------------------------------------- |
| Document Version | 2.0                                                                    |
| Date             | May 10, 2026                                                           |
| Author           | Pallav Chaturvedi                                                      |
| Status           | Design — supersedes v1.8 platform PRD                                  |
| Classification   | Confidential                                                           |
| Primary Audience | Group CFO, Group CEO, Audit Committee Chair, Cost Transformation Lead  |
| Reporting Currency | INR (Indian Rupees, ₹). Multi-currency supported.                    |
| Engagement Model | 12-week diagnostic sprint, deployed in client environment             |

---

## What Changed from v1.8

v1.8 specified a *platform*. v2.0 specifies an *asset for a 12-week diagnostic engagement*. The engine is largely retained; the framing, security posture, sector adaptability, and outputs are re-architected for use inside large Indian enterprises by an external advisory team.

| Dimension              | v1.8                                          | v2.0                                                                          |
| ---------------------- | --------------------------------------------- | ----------------------------------------------------------------------------- |
| Buyer / user           | FP&A analyst, procurement analyst, consultant | Group CFO + Cost Transformation Office (executive sponsors); analysts operate |
| Currency / geography   | USD-default, US benchmarks                    | INR-default, Indian benchmarks (CMIE, CRISIL, BRSR), multi-currency capable   |
| Deployment             | Single-tenant SaaS implied                    | Client-environment deployment (VPC / on-prem) + tear-down protocol            |
| Data security          | Not addressed beyond basic input validation   | DPDP Act 2023, RBI/SEBI/IRDAI sectoral rules, data sovereignty, key management |
| LLM data flow          | Anthropic API direct                          | Configurable: regional Bedrock/Azure OpenAI, on-prem LLM, or determinism-only |
| Sector adaptability    | One generic taxonomy                          | Core taxonomy + plug-in sector packs (BFSI, Mfg., IT/ITeS, Pharma, FMCG, etc.) |
| Engagement structure   | Open-ended platform usage                     | Defined 12-week sprint with weekly deliverables and decision gates             |
| Output for C-suite     | .docx export of business case                 | One-page brief, board deck, live cost room, MOR pack, PMO toolkit              |
| Value framing          | NPV, payback, IRR                             | bps EBITDA, ΔROCE, ΔEPS, ΔFCF — translated to shareholder narrative           |
| Confidence scoring     | Mechanical 0.5/0.75/0.9 multiplier            | Assumption register + P10/P50/P90 ranges + single-variable sensitivity        |

---

## 1. Executive Summary

### 1.1 What This Is

A **12-week cost diagnostic asset** that an advisory team deploys inside a client enterprise to identify, size, and stage 12–24 months of operating expenditure savings. It combines an agentic analytical engine (carried forward from v1.8) with a defined engagement playbook, executive output set, and security architecture that satisfies Indian enterprise IT and audit committee requirements.

### 1.2 What It Delivers

By Week 12 the client has:

1. A **diagnosed cost base** segmented into addressable, semi-addressable, and locked, with peer-position for every material pool.
2. A **prioritised initiative portfolio** of typically 30–80 initiatives, each with owner, gross/net savings range, cost-to-achieve, payback, EBITDA bps, and a P10/P50/P90 range.
3. A **board-ready narrative** — one-page CFO brief, 15-slide board deck, and a sensitivity-aware "cost room" the CFO can run live in front of the Audit Committee.
4. A **live PMO and MOR cadence** — initiative tracker, monthly operating review pack template, audit-grade traceability from each ₹ of committed savings back to source data.
5. A **tear-down protocol** — all client data exfiltrated, encrypted, returned or destroyed per agreed schedule, with attestation.

### 1.3 Why It's Different

- **Indian-context-native.** Built around INR, GST input credit mechanics, Ind AS, BRSR, CMIE/CRISIL benchmarks, RBI/SEBI/IRDAI rules — not adapted from a US tool.
- **Sector-pack architecture.** Same engine, plug-in sector modules. A consultant can deploy at an HDFC, a Tata Steel, an Infosys, a Sun Pharma, or a Reliance Retail and have the right taxonomy, benchmarks, and levers within Day 1.
- **Built for client trust.** Default deployment is inside the client's own AWS/Azure India tenancy or on-prem; data never leaves client perimeter; LLM calls are routed to regional models with zero data retention; tear-down is contractual.
- **Built for the C-suite, not the analyst.** Every number traces upward to a board narrative; every assumption is named, ranged, and challengeable.

### 1.4 What This Is *Not*

| It is NOT                                       | It IS                                                                |
| ----------------------------------------------- | -------------------------------------------------------------------- |
| A SaaS product clients sign up to               | An asset deployed *into* a client's environment for a defined sprint |
| A replacement for the consulting team           | A force multiplier — collapses ~12 weeks of analyst work into ~3     |
| A live ERP integration / always-on dashboard    | A snapshot-based diagnostic with monthly refresh during sprint       |
| An execution platform for the cost programme    | A diagnostic + commitment platform; execution remains client-owned   |
| An audit substitute                             | An assumption-disclosed input to audit; not statutory output         |

---

## 2. Problem Statement (C-Suite Reframed)

### 2.1 The Indian Enterprise Cost Pressure

Listed Indian enterprises operate under a margin-compression environment that has structurally tightened since 2024:

- **Topline pressure.** Consensus EBITDA growth for the BSE 500 trails revenue growth in 7 of the last 10 quarters; margin defence is the dominant earnings lever.
- **Cost inflation differentials.** Wage inflation (8–11% for skilled roles) outpaces pricing power (3–6% in most categories) and CPI (4–6%). The wedge compounds annually.
- **Capital efficiency mandate.** Investor focus has shifted from growth-at-any-cost to ROCE and FCF; promoter groups, PE/VC backers, and FII investors increasingly evaluate management on capital efficiency.
- **Regulatory load.** BRSR for top 1,000 listed; DPDP Act compliance from 2024–25; new labour codes; GST e-invoicing thresholds; Section 43B(h) MSME 45-day rule. Each adds discrete cost.
- **Capability gap inside finance teams.** Most Indian groups have small central FP&A teams. Cost diagnostics are episodic, externally led, and typically take 16–24 weeks at ₹4–8 Cr per engagement.

### 2.2 The C-Suite Pain

| Persona                        | What keeps them up                                                                                     | Where today's tools fail them                                                  |
| ------------------------------ | ------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------ |
| Group CEO / MD                 | Margin guidance to the street; analyst-call narrative; capital allocation                              | No single view of cost-out potential; depends on quarterly consultant snapshots |
| Group CFO                      | EBITDA defence; FCF; ROCE; commitment to board; audit committee defensibility                          | Pipeline of "ideas" never converts to booked savings; numbers don't tie to GL  |
| Audit Committee Chair          | Provenance and audit-grade traceability of management commitments                                      | Excel-based business cases, no assumption register, no source-of-truth         |
| CHRO                           | People costs (30–50% of OpEx in services/BFSI); attrition vs. cost lever tension                       | Headcount levers always overstated; no link to span-and-layer benchmarks       |
| Cost Transformation Lead       | Day-to-day execution; PMO load; initiative attrition month-on-month                                    | No system of record; spreadsheet sprawl; no forecast-to-complete logic         |
| Promoter / Family Office       | Group-level value-up; cross-entity efficiency; related-party hygiene                                   | No conglomerate view; intra-group costs invisible                              |

### 2.3 The Cost of Inaction

For a typical ₹15,000–50,000 Cr revenue Indian major:

- **Run-rate addressable opex** is conservatively 8–12% of revenue, or ₹1,200–6,000 Cr.
- **Realistic 18-month savings capture** is 1.5–3% of revenue, or ₹225–1,500 Cr.
- **Translation to shareholder value** at 15–20× P/E is ₹3,400–30,000 Cr of market-cap upside, before re-rating effects.

Today the typical cost of *finding* this opportunity (16–24 week consulting engagement) runs ₹4–8 Cr; the typical cost of *not finding part of it* (initiatives missed, mis-sized, or never executed) is 30–50% of the opportunity.

---

## 3. The Asset & Engagement Model

### 3.1 Asset Definition

The asset has four components, packaged for repeat deployment:

| Component                | Contents                                                                                                                                         |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Engine**               | OPAR loop, skills runtime, deterministic analysers, LLM connectors, memory layer (carried forward from v1.8 with security and India enhancements) |
| **Sector Packs**         | Plug-in modules per sector: extended taxonomy, sector-specific benchmarks, sector levers, regulatory layer, sector KPIs, sector deck templates    |
| **Engagement Playbook**  | 12-week week-by-week activity guide, RACI, decision gates, deliverable templates, MOR cadence                                                     |
| **Deployment Toolkit**   | Infrastructure-as-code for client-VPC and on-prem deployment, security hardening guide, tear-down runbook                                         |

### 3.2 Engagement Lifecycle

```
[Pre-engagement: 1-2 weeks]  →  [12-week sprint]  →  [Tear-down: 1 week]  →  [Optional 90-day support]
```

| Stage                | Duration   | Key Activities                                                                                |
| -------------------- | ---------- | --------------------------------------------------------------------------------------------- |
| Pre-engagement       | 1–2 weeks  | NDA, DPA, client InfoSec review, deployment site selection, sector pack selection, kickoff prep |
| Diagnostic sprint    | 12 weeks   | Full OPAR-driven analysis to board commitment (see §13)                                       |
| Tear-down            | 1 week     | Data exfiltration to client, anonymised aggregates retained per consent, env destruction, attestation |
| Post-sprint support  | 90 days    | Optional MOR support, initiative tracker hosting, CFO office check-ins                        |

### 3.3 Repeatability

The asset is designed for ~80% reuse across engagements. Per engagement, the variable work is:
- Sector pack configuration (1–3 days; often pre-existing)
- Client-specific taxonomy mapping override (1–2 days)
- Industry-specific peer set selection (0.5 day)
- Output deck branding (0.5 day)
- Deployment & access provisioning (2–3 days)

Total variable setup: ~7–10 person-days per engagement; everything else is templated.

---

## 4. Goals, Non-Goals, Personas

### 4.1 Goals

**Engagement goals (per deployment):**

- Surface ₹X Cr of addressable spend by end of Week 4, with peer position, at sufficient resolution to triage.
- Convert ₹0.6X Cr to a committed initiative portfolio by end of Week 8, with named owners.
- Produce a board-ready narrative by end of Week 11, defensible to Audit Committee.
- Stand up a self-sustaining PMO + MOR cadence by end of Week 12.

**Asset goals (across deployments):**

- Compress diagnostic cycle from 16–24 weeks to 12 weeks at parity or better quality.
- Enable a single Manager + 2 Analyst engagement team to deliver what previously needed Manager + Senior Manager + 4 Analysts.
- Achieve client InfoSec / DPO sign-off in <10 working days for ≥80% of deployments.
- Maintain audit-grade traceability from every committed ₹ to source data.

### 4.2 Non-Goals (v2.0)

| Non-Goal                                          | Rationale                                                                                              |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| Real-time ERP integration                         | Snapshot-based extracts (monthly refresh during sprint) sufficient for diagnostic; v3 capability        |
| Execution platform for the cost programme         | Hand off to client tooling (Jira, ServiceNow, ARIBA) at end of sprint; PMO tracker is the bridge       |
| Always-on multi-client SaaS                       | Engagement-scoped deployment is the security and commercial model; SaaS is a future variant            |
| Statutory accounting outputs                      | Diagnostic only; statutory close, audit, regulatory filings remain in client's existing systems        |
| Vendor-of-record for benchmark data licenses      | Client either holds CMIE / CRISIL / Capitaline licenses or contracts these directly                    |
| Replacement for change management capability      | Behavioural and organisational change remains a human-led consulting workstream                        |

### 4.3 Personas

| Persona                                | Role in engagement                                          | What they need from the asset                                                                |
| -------------------------------------- | ----------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| **Group CFO** (executive sponsor)      | Owns the engagement, presents to board                      | One-page brief; defensible numbers; sensitivity controls; commitment-to-realisation traceability |
| **Group CEO / MD**                     | Receives the narrative                                      | Margin / ROCE / EPS impact; competitive position; capital ask                                  |
| **Audit Committee Chair**              | Reviews and challenges                                      | Assumption register; provenance; control evidence                                              |
| **Cost Transformation Lead** (PMO)     | Day-to-day client owner; runs MOR                            | Live tracker; initiative status; FTC; at-risk flagging                                         |
| **Functional Owners** (CFO, CHRO, CIO, CPO, COO) | Own specific cost pools                          | Pool-level deep-dive; lever options with confidence; peer benchmarks                          |
| **Engagement Manager** (advisory)      | Runs the 12-week sprint                                     | Playbook adherence; deliverable templates; quality control                                    |
| **Engagement Analyst** (advisory)      | Operates the asset day-to-day                               | Skills UI; data ingestion controls; output review; assumption capture                          |
| **Client InfoSec / DPO**               | Approves deployment                                         | Security architecture doc; DPA; data flow diagram; tear-down attestation                       |

---

## 5. Security & Data Sovereignty Architecture

This section is the most material change vs. v1.8. Data security is the **first** question every Indian Group CFO and InfoSec head asks about an external diagnostic asset. The answer below should be sufficient to clear most Indian enterprise InfoSec gates in <10 working days.

### 5.1 Design Principles

1. **Client data never leaves the client perimeter.** Default deployment is inside the client's own cloud tenancy (AWS / Azure / GCP India region) or on-prem.
2. **Engagement data is short-lived.** All client data is destroyed at tear-down; only anonymised aggregate metadata is retained, and only with explicit consent.
3. **LLM calls do not transmit raw client data.** Three data-flow modes (§5.4); the default mode for sensitive sectors is determinism-first with masked context.
4. **Compliance-by-construction with Indian regulation.** DPDP Act 2023, RBI circulars on data localisation (BFSI), SEBI guidelines (capital markets), IRDAI norms (insurance), CERT-In incident reporting (6-hour rule).
5. **Audit trail by default.** Every data access, every skill invocation, every export is logged to an immutable audit log that the client controls.

### 5.2 Deployment Models

| Model                                  | Where it runs                                              | When to use                                                         | Spin-up time |
| -------------------------------------- | ---------------------------------------------------------- | ------------------------------------------------------------------- | ------------ |
| **A. Client VPC (recommended)**        | Inside client AWS / Azure / GCP tenancy in Indian region   | Default for all engagements; sufficient for ≥85% of clients         | 2–3 days     |
| **B. On-prem appliance**               | Inside client data centre, behind client firewall          | BFSI under RBI data localisation; defence/PSU; high-sensitivity IP   | 5–7 days     |
| **C. Air-gapped offline**              | Engagement-team laptop, no inbound/outbound network        | Pre-IPO, M&A target diagnostics, family-office sensitive scenarios   | 1 day         |
| **D. Isolated SaaS (last resort)**     | Advisory firm's AWS Mumbai with single-tenant isolation    | Smaller clients (<₹2,000 Cr revenue) without internal cloud capacity | <1 day       |

In all four models, the asset behaviour is identical from the user's perspective; only the infrastructure substrate changes. Configuration is via deployment toolkit (Terraform + Ansible).

### 5.3 Data Classification & Handling

Every data element ingested is auto-classified into one of four bands; handling rules differ by band.

| Band               | Examples                                                              | Handling                                                                 |
| ------------------ | --------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| **B1: Public**     | Industry reports, BSE/NSE filings, BRSR disclosures                   | No restrictions; can leave client perimeter                              |
| **B2: Confidential** | Aggregate spend cubes, category totals, vendor counts                 | Stays in client VPC; can be passed to LLM in summarised form             |
| **B3: Restricted** | Vendor names, contract values, individual transactions, GL line items | Stays in client VPC; LLM access only via masking/tokenisation            |
| **B4: PII / Regulated** | Employee names, PAN, Aadhaar, salary details, customer data        | **Stripped at ingestion**; never enters analytical pipeline; no LLM access |

The ingestion pipeline includes a **PII stripper** that scans incoming files using regex + NER and removes B4 fields before storing to the analytical store. The stripped originals are retained (encrypted) only for audit; the working dataset has no PII.

### 5.4 LLM Data-Flow Modes

The platform supports three configurable LLM modes, selected at deployment based on client InfoSec posture and sector regulation.

| Mode                     | Description                                                                                                                            | When to use                                                       |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| **M1: Determinism-first** | All numerical analysis is deterministic (Python). LLM is invoked only for narrative drafting on B2 (summarised) data.                 | Default for BFSI, healthcare, defence, regulated sectors          |
| **M2: Regional managed LLM** | LLM calls routed to AWS Bedrock (Mumbai), Azure OpenAI (Pune/Central India), or Anthropic via dedicated India endpoint with no data retention. Data masking applied. | Default for most other sectors                              |
| **M3: On-prem LLM**       | Open-weight model (Llama 3.1 70B, Mistral Large) hosted on client GPU. Higher latency, lower fidelity, full data sovereignty.        | Air-gapped deployments; classified data; M&A target diagnostics  |

**Critical rule:** in modes M1 and M2, no B3 or B4 data is ever sent to any LLM. The `llm-context-builder` skill enforces this by rebuilding context from B2 summaries only, with B3 entities replaced by tokens (e.g. `<vendor_237>`, `<gl_account_4500>`).

### 5.5 Indian Regulatory Compliance

| Regulation                                                | Requirement                                                                                          | How the asset complies                                                                                           |
| --------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| **DPDP Act 2023**                                         | Lawful processing of personal data; data minimisation; purpose limitation; storage limitation         | PII stripper at ingestion; processing log; consent register; tear-down protocol enforces storage limitation       |
| **RBI Master Direction on Data Localisation** (BFSI)      | Payment system data localised in India; certain data prohibited from cross-border transfer            | Deployment models A, B, C with India-region only; LLM modes M1 or M3 only for in-scope BFSI data                  |
| **SEBI System Audit Framework**                            | Audit logs for all access to material non-public information                                          | Immutable audit log with WORM storage; client retains log post-engagement                                         |
| **IRDAI Information & Cybersecurity Guidelines** (Insurance) | Risk-based controls; periodic VAPT; incident reporting                                              | VAPT report per release; incident playbook integrated with client SOC                                             |
| **CERT-In Direction (Apr 2022)**                          | 6-hour cyber incident reporting; 180-day log retention                                               | Audit logs retained 180 days minimum; incident response runbook included in deployment toolkit                    |
| **Companies Act 2013, Section 138** (Internal Audit)      | Internal audit of material processes                                                                 | Engagement runbook designed to be auditable; assumption register supports internal audit review                   |

### 5.6 Encryption, Access, Audit

| Control          | Specification                                                                                                                                    |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| At-rest          | AES-256 via client KMS (AWS KMS / Azure Key Vault / on-prem HSM). No engagement-side keys.                                                       |
| In-transit       | TLS 1.3 minimum, mutual TLS for inter-service calls, certificate pinning for LLM endpoints                                                       |
| Authentication   | SSO via client IdP (Okta, AAD, Ping); MFA mandatory; no local user accounts                                                                      |
| Authorisation    | RBAC: 4 roles — Sponsor (read-only outputs), Analyst (read/write data), Admin (deployment), Auditor (read all logs). Principle of least privilege |
| Network          | Client VPC with no public ingress; egress restricted to allowlisted endpoints (LLM, benchmark sources); VPC flow logs to client SIEM             |
| Audit log        | Append-only, integrity-hashed, exported to client SIEM (Splunk, Sentinel, QRadar) in real time                                                   |
| Secrets          | No secrets in code or config; runtime fetched from client secrets manager (HashiCorp Vault, AWS Secrets Manager)                                  |
| Vulnerability    | Container images scanned (Trivy); dependencies scanned (Snyk); quarterly penetration test; CVE-driven patch SLA: critical 24h, high 72h          |

### 5.7 Tear-Down Protocol

Mandatory at engagement end. Client receives written attestation.

| Step | Day | Action                                                                                                              |
| ---- | --- | ------------------------------------------------------------------------------------------------------------------- |
| 1    | T-7 | Final data export to client-specified S3/Blob/SFTP destination (encrypted with client key)                          |
| 2    | T-3 | Aggregate anonymised metrics (pool sizes, lever savings %, benchmark gaps) saved to advisory's repository — only if client consent obtained at SoW signing |
| 3    | T-0 | All compute and storage destroyed. Backups deleted. Logs handed over.                                               |
| 4    | T+1 | Tear-down attestation signed by Engagement Partner and Client InfoSec. Audit trail of destruction provided.         |
| 5    | T+30 | Independent verification: client InfoSec confirms no residual access via control-plane audit                       |

### 5.8 The Trust Pitch

The asset's security architecture exists to answer one question from a Group CFO or Audit Committee: *"If I let your team take our spend data, how do I know it doesn't end up training someone's AI or sitting on a consultant's laptop after they leave?"* The answer is a one-page diagram (§17.D) showing: client-perimeter deployment, India-region LLM endpoints with no retention, PII stripping at ingest, immutable audit log streamed to client SIEM, contractual tear-down with attestation, and zero engagement-side persistent storage of B3/B4 data.

---

## 6. Sector Module Framework

### 6.1 Why Sector Packs

Cost composition, lever availability, regulatory constraints, peer set, and board narrative differ materially by sector. A generic taxonomy applied to a bank produces nonsense (no view of branch network rationalisation, no view of tech-stack opex which is 60% of the addressable base). The sector pack abstraction lets the engine remain stable while sector-specific intelligence plugs in.

### 6.2 Pack Anatomy

Every sector pack is a self-contained directory with the following structure:

```
sector_packs/
  bfsi_banks/
    pack_manifest.yaml           # version, dependencies, applicable peer set
    taxonomy_extension.json      # sector categories beyond the generic 25
    benchmark_sources.yaml       # which datasets, which queries, which fields
    sector_levers.json           # levers unique to this sector with default ranges
    regulatory_layer.md          # in-force regulations affecting cost decisions
    kpi_pack.json                # sector C-suite KPIs (cost/income, opex/AAUM)
    peer_set.json                # listed Indian peers with ticker + segment
    deck_template.pptx           # sector-flavoured board narrative
    one_page_brief.docx          # CFO brief template
    sample_outputs/              # anonymised sample outputs for sales conversations
  bfsi_insurance/
  manufacturing_steel/
  manufacturing_cement/
  manufacturing_auto/
  it_ites_services/
  pharma_formulations/
  fmcg_diversified/
  retail_organised/
  telecom/
  energy_utilities/
  conglomerate_diversified/      # default for multi-sector groups
```

### 6.3 Pack Selection at Engagement Kickoff

| Step | Activity                                                                                                                       |
| ---- | ------------------------------------------------------------------------------------------------------------------------------ |
| 1    | Engagement team identifies primary sector + secondary sectors (for diversified groups)                                         |
| 2    | Asset deploys with primary pack as default; secondary packs loaded for specific BUs                                            |
| 3    | Conglomerate clients use `conglomerate_diversified` as the spine, with sector packs activated per BU during ingestion          |
| 4    | Pack version is locked at engagement start (no mid-engagement upgrades to avoid moving-target benchmarking)                    |

### 6.4 Worked Example A — BFSI / Banks Pack

**Why this sector matters first.** Indian banking has the highest opex-to-revenue ratio of any major listed segment (cost-to-income typically 38–52%); a 200 bps reduction in CIR is worth ₹500–2,000 Cr to a top-10 bank. Tech opex inside Indian banks has tripled in 5 years. Branch network rationalisation is politically sensitive but financially material.

**Extended taxonomy (additions to generic 25):**

| Category                            | Typical % of BFSI opex | Example sub-categories                                         |
| ----------------------------------- | ---------------------- | -------------------------------------------------------------- |
| Branch network                      | 18–28%                 | Branch rent, branch staff, branch utilities, ATM network        |
| Technology — core banking           | 8–14%                  | Core banking platform, channels, middleware, data centre        |
| Technology — digital channels       | 4–8%                   | Mobile/web, UX, APIs, customer onboarding                       |
| Risk, compliance, audit              | 4–7%                   | KYC/AML tooling, model risk, internal audit, regulatory reporting |
| Customer acquisition cost (CASA)    | 3–6%                   | Sourcing fees, DSA payouts, branch acquisition incentives        |
| Collections & recovery              | 2–5%                   | Collection agencies, legal recovery, debt sale infrastructure   |
| Treasury & ALM operations           | 1–3%                   | Treasury systems, dealer infrastructure, regulatory treasury reporting |
| Card operations                     | 1–4%                   | Card production, fraud monitoring, scheme fees (Visa/Mastercard/RuPay) |

**Sector-specific levers:**

| Lever                                         | Methodology                                                                                                | Typical capture                  |
| --------------------------------------------- | ---------------------------------------------------------------------------------------------------------- | -------------------------------- |
| Branch network rationalisation                | Footfall/transaction-density analysis vs. cost-to-serve; thin-branch and assisted-digital model            | 8–18% of branch opex             |
| Digital channel migration                     | Transaction-mix shift; cost-per-transaction delta (branch ₹50–80 vs digital ₹3–8)                          | 5–12% of total opex              |
| Core banking simplification / consolidation   | Multi-platform → single; legacy decommissioning                                                            | 15–30% of core banking spend      |
| Model risk infrastructure consolidation       | Multiple ML/scoring platforms → unified MLOps                                                              | 20–35% of model risk spend       |
| KYC/AML utility shift                         | Captive → utility/CKYC-led                                                                                 | 25–40% of KYC operations cost     |
| DSA channel rationalisation                   | DSA productivity tail-cut; commission renegotiation                                                        | 8–15% of CASA acquisition cost    |
| Real estate consolidation                     | Corporate office consolidation; tier-2 city back-office shift                                              | 10–22% of corp real estate spend  |

**Regulatory layer:**

- RBI Master Direction on Outsourcing of IT Services (Apr 2023) — restricts certain outsourcing; affects cost-to-achieve calculations
- RBI MD on Information Technology Governance (Nov 2023) — IT governance investment floor
- RBI Data Localisation circular (Apr 2018) — payment data localisation; affects cloud cost models
- DPDP Act 2023 — customer data; affects MarTech and analytics spend
- IRDAI Outsourcing Regulations (insurance subs) — restricts insurance opex levers

**KPIs surfaced in C-suite output:**

| KPI                                | Why it matters                              | Target movement on board deck         |
| ---------------------------------- | ------------------------------------------- | -------------------------------------- |
| Cost-to-Income Ratio (CIR)         | Primary efficiency metric; analyst-tracked  | bps reduction over 18 months           |
| Opex / Average Assets              | Asset-base normalised efficiency            | bps reduction                          |
| Cost per Customer                  | Productivity proxy                          | ₹ reduction per customer                |
| Branch Productivity (PPC, ATM/branch) | Network efficiency                          | Multiples improvement                  |
| Tech opex / Total opex             | Tech investment intensity                   | Stable or controlled drift             |

**Peer set (default):** HDFC Bank, ICICI Bank, Axis Bank, Kotak Mahindra, IndusInd, SBI (where applicable), Federal Bank, RBL, IDFC First. Pack supports peer set override per engagement.

### 6.5 Worked Example B — Manufacturing (Diversified) Pack

**Why this sector matters.** Indian manufacturing carries 60–75% variable cost (raw materials + conversion); only 25–40% is true OpEx in the FP&A sense. The asset focuses on the conversion + indirect band, where peer dispersion is widest and benchmark data (CMIE, sector associations) is richest.

**Extended taxonomy (additions to generic 25):**

| Category                                    | Typical % of Mfg. opex (ex-RM) | Example sub-categories                                            |
| ------------------------------------------- | ------------------------------ | ----------------------------------------------------------------- |
| Power & utilities                           | 12–28%                         | Grid, captive (coal/gas/solar), open access, water, fuel oil      |
| Maintenance — plant & machinery             | 8–15%                          | Spares, AMCs, shutdown maintenance, predictive maintenance        |
| Inbound + outbound logistics                | 10–22%                         | Freight (road/rail/coastal), warehousing, demurrage, last-mile     |
| Plant overheads                             | 5–10%                          | Security, housekeeping, canteen, transport                         |
| Quality & R&D                               | 2–6%                           | Lab, testing, certification, formulation R&D                       |
| Packaging materials                         | 4–8% (sector-dependent)        | Primary, secondary, tertiary; sustainable packaging premium       |
| Stores & consumables                        | 3–7%                           | Lubricants, chemicals, indirect stores                             |
| Pollution control & ESG compliance          | 1–3%                           | ETP/STP opex, RPO, BRSR-driven                                     |

**Sector-specific levers:**

| Lever                                         | Methodology                                                                       | Typical capture                  |
| --------------------------------------------- | --------------------------------------------------------------------------------- | -------------------------------- |
| Energy mix optimisation                       | Captive vs. open access vs. grid; renewable PPA; solar rooftop                    | 12–28% of power cost             |
| Plant utilisation lift (OEE)                  | Bottleneck removal, changeover reduction, maintenance shift                        | 6–14% of conversion cost          |
| Modal shift (road → rail / coastal)           | Volume + lane analysis under PMP/Gati Shakti                                      | 15–30% of logistics cost          |
| Vendor base rationalisation                   | Tail-spend cut; HHI rebalance; reverse auctions                                    | 8–18% of indirect spend           |
| Inventory + working capital                   | DIO reduction; vendor-managed inventory                                            | Working capital release ₹/Cr      |
| Maintenance shift (TBM → CBM/predictive)      | Sensor-led predictive; RUL modelling                                              | 12–25% of maintenance spend       |
| Make vs. buy reset (captive shared services)  | GIC/GCC vs. outsourcing vs. captive                                                | 15–30% of indirect labour spend   |

**Regulatory layer:**

- Factories Act 1948 — minimum staffing, safety; constrains some overhead cuts
- Pollution Control Board norms (state-by-state) — ETP/STP minimum spend
- Renewable Purchase Obligation — 25–40% RPO by 2030; drives energy mix
- BRSR (top 1,000 listed) — must report energy/water/waste intensity; cost lever has ESG co-benefit
- PLI scheme participation — affects make-vs-buy economics in 14 sectors

**KPIs surfaced in C-suite output:**

| KPI                                | Why it matters                              | Target movement on board deck         |
| ---------------------------------- | ------------------------------------------- | -------------------------------------- |
| Conversion cost / MT (or unit)     | Primary plant efficiency                    | ₹/MT reduction                         |
| Energy intensity (kWh / MT)        | Sustainability + cost                       | % reduction with BRSR co-benefit       |
| OEE (Overall Equipment Effectiveness) | Asset productivity                          | Percentage points improvement          |
| Logistics cost / revenue            | Network efficiency                          | bps reduction                          |
| EBITDA / MT                         | Bottom-line per unit                        | ₹/MT improvement                       |
| Cash conversion cycle               | Working capital                             | Days reduction                         |

**Peer set (illustrative — varies by sub-sector):**

- Steel: Tata Steel, JSW Steel, JSPL, SAIL
- Cement: UltraTech, Ambuja, Shree Cement, Dalmia Bharat
- Auto: Tata Motors, Mahindra, Bajaj Auto, Hero MotoCorp
- Chemicals: Pidilite, SRF, UPL, Tata Chemicals

### 6.6 Other Sector Packs (Templates)

Each follows the same anatomy. Below is the at-a-glance taxonomy headline + 2 distinctive levers per pack. Full pack development is a 5–8 day effort each; the asset ships with the BFSI and Manufacturing packs as worked examples and 9 templates as scaffolds.

| Sector pack                | Distinctive cost categories                                                       | Two distinctive levers                                                                          |
| -------------------------- | --------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| **IT / ITeS Services**     | Bench cost, project delivery overheads, rate-card vs. cost differential, real estate, travel | Bench optimisation; pyramid restructuring (juniorisation)                                       |
| **Pharma — Formulations**  | R&D, regulatory affairs, plant compliance (USFDA / EU GMP), API procurement, MR force | API source diversification (China dependency reduction); MR productivity & territory rationalisation |
| **FMCG — Diversified**     | A&P spend, depot network, primary and secondary freight, distributor margin pool   | Trade promo ROI rationalisation; depot footprint right-sizing                                   |
| **Retail — Organised**     | Store network, store labour, supply chain, technology, marketing                  | Store productivity tier reset (close bottom 10%); private label margin shift                    |
| **Telecom**                | Network opex (passive + active), spectrum charges, customer acquisition, IT       | Tower-tenancy renegotiation; customer service AI deflection                                     |
| **Energy & Utilities**     | Fuel, transmission losses, manpower, regulatory levies, AMC                       | T&D loss reduction programmes; renewable integration shift                                      |
| **Conglomerate (default)** | All of the above + corporate centre, group-shared services, related-party flows   | Corporate centre rationalisation; shared services pricing reset                                 |
| **Pre-IPO / M&A target**   | Standardised due-diligence taxonomy; quality-of-earnings overlay                  | One-time cost identification; addback hygiene                                                    |
| **PSU / Government**       | Manpower-heavy structures, regulatory mandates, social obligations                | VRS economic case; outsourceable function identification                                        |

### 6.7 Pack Governance

- **Versioning.** Semantic versioning per pack (e.g., `bfsi_banks-v1.4.0`); engagement locks to a specific version.
- **Release cadence.** Quarterly review; major version on significant regulatory or benchmark refresh.
- **Pack-level testing.** Each pack has a golden dataset (anonymised sample client) and a regression suite; release blocked on regression failure.
- **Pack maintenance ownership.** One senior advisor per pack; reviewed and signed off by sector lead each quarter.

---

## 7. India Context Layer

The India context layer is *cross-cutting* — it permeates every skill, every output, every deployment. It is not a sector pack; it is the spine.

### 7.1 Currency & Number Formatting

- **Default reporting currency:** INR.
- **Display format:** Indian numbering system (Lakh / Crore) for executive outputs; international (millions / billions) toggle available for global investor decks.
- **Multi-currency input.** Spend lines may be in any currency; FX normalisation to INR using configurable rates (RBI reference rate default; client-specific rates supported).
- **FX volatility surface.** Macro sensitivity skill (§9) includes INR-USD, INR-EUR, INR-CNY scenarios for import-heavy sectors.

### 7.2 Tax Layer

| Element                              | Treatment in the asset                                                                                      |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------- |
| **GST input tax credit (ITC)**       | Per-line ITC eligibility flagged; ineligible credits surfaced as a discrete savings opportunity              |
| **Reverse charge mechanism (RCM)**    | Identified for legal, transport, security, sponsorship; cash flow + ITC impact modelled                     |
| **Inverted duty refund**              | Triggered for sectors with lower output GST than input GST (textiles, fertilizer); refund cycle modelled    |
| **TDS / TCS reconciliation**          | TDS leakage surfaced; vendor 26AS mismatch flagged; cash flow drag quantified                               |
| **Section 115BAA election**           | 22% concessional regime impact on after-tax NPV of initiatives                                              |
| **MAT credit utilisation**            | Where applicable, after-tax NPV adjusted for MAT credit position                                            |
| **CSR (Section 135)**                 | Mandatory 2% of avg net profit; treated as fixed; *not* subject to "savings" lever                          |
| **DDT / Buyback tax**                 | Capital allocation alternatives modelled in shareholder bridge (§10)                                        |

### 7.3 Accounting Standards

- **Ind AS 116 (Leases).** Operating leases on balance sheet; lease modifications affect both opex and balance sheet; the asset reports both cash savings and Ind AS 116 P&L impact for real-estate levers.
- **Ind AS 102 (Share-based payment).** ESOP/RSU cost is a P&L expense; the asset includes ESOP rationalisation as a discrete lever.
- **Ind AS 19 (Employee benefits).** Gratuity actuarial valuation; the asset surfaces gratuity assumption sensitivity in people-cost levers.
- **Schedule III disclosure.** Related-party transactions surfaced; intra-group cost flows mapped before benchmarking to avoid double-counting.

### 7.4 Indian Benchmark Sources

The single biggest unlock vs. v1.8. Replaces / augments IBISWorld / Hackett / Gartner with India-relevant sources.

| Source                                  | Coverage                                                              | Access                                          | Refresh    |
| --------------------------------------- | --------------------------------------------------------------------- | ----------------------------------------------- | ---------- |
| **CMIE Prowess IQ**                     | Line-item financials of all listed Indian companies; 50+ years history | Annual licence; queryable via API                 | Quarterly  |
| **Capitaline Plus**                     | Listed financials, sector aggregates, peer comparison                  | Licence; bulk export                            | Quarterly  |
| **CRISIL Industry Reports**             | Sector cost structures, capex/opex norms                              | Per-report purchase or annual subscription       | Annual     |
| **ICRA / India Ratings sector reports** | Sectoral cost benchmarks                                               | Per-report purchase                             | Annual     |
| **MCA21 / AOC-4 filings**               | Audited financials of unlisted entities (subs, JV partners)            | Free public data                                 | Annual     |
| **BSE / NSE filings + earnings calls**  | Peer commentary on cost programmes, headcount, capex; mined automatically | Free public data; processed by `peer-disclosure-miner` | Quarterly  |
| **BRSR disclosures**                    | Energy / water / waste / employee intensities for top 1,000           | Free, mandatory                                 | Annual     |
| **CII / FICCI / NASSCOM sector studies** | Process and operational benchmarks                                     | Member access; some public                      | Periodic   |
| **RBI Statistical Tables, IBA bulletins** | Banking sector benchmarks                                              | Free                                            | Quarterly  |
| **CEA reports** (energy)                | Tariff, generation, transmission benchmarks                            | Free                                            | Periodic   |
| **PIB / sectoral ministry data**         | Subsidy, regulatory, programme data                                    | Free                                            | Periodic   |
| **Anonymised platform-derived (Tier 3)** | Aggregated savings rates from prior engagements                        | Internal; consent-based                         | Per engagement |

The asset ships with connectors / parsers for the free sources (MCA21, BSE/NSE, BRSR, RBI, CEA) and with adapter stubs for the paid sources (client provides licence / credentials).

### 7.5 BRSR / ESG Co-Benefit Layer

For SEBI top-1000 listed entities, BRSR disclosures are mandatory. Most cost optimisation levers carry direct BRSR positives. The asset surfaces this explicitly:

| Cost lever                          | BRSR co-benefit                                                       |
| ----------------------------------- | --------------------------------------------------------------------- |
| Energy mix shift to renewable       | Scope 2 emissions reduction (Section A, Principle 6)                  |
| Logistics modal shift               | Scope 3 emissions reduction (Principle 6)                             |
| Real estate consolidation           | Energy + water + waste reduction (Principle 6)                        |
| Vendor consolidation                | Supply chain due diligence improvement (Principle 8)                  |
| Digital channel migration (BFSI)     | Paper / energy reduction (Principle 6)                                |
| Captive shared services consolidation | Employee well-being / training data improvement (Principle 3)         |

Each initiative in the output is tagged with its BRSR principle linkage; the board narrative includes a "cost out + ESG forward" framing where applicable.

### 7.6 Conglomerate / Group Structure Handling

| Element                              | Treatment                                                                                                      |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------- |
| Inter-company transactions           | Identified at ingestion via party master / GL flag; eliminated before peer benchmarking                        |
| Related-party (Sec 188) spend        | Surfaced as a separate band; benchmarked against arm's-length range; lever = renegotiation or unbundling       |
| Group shared services pricing        | Allocations decomposed; underlying cost re-benchmarked at activity level                                       |
| Captive vs. third-party flow         | Both sides shown; make-vs-buy reset modelled at group level                                                    |
| Holding-company costs                | Treated as a separate cost pool; benchmarked against listed holdcos (Bajaj Holdings, etc.)                     |

---

## 8. OPAR Engine (Carry-Forward, Simplified)

The OPAR loop from v1.8 / OPAR Loop Specification is largely retained. Only the changes needed for v2.0 are described here. Refer to the original OPAR specification for the unchanged depth.

### 8.1 What Stays

- Four-phase loop (Observe → Plan → Act → Reflect) owned by the orchestrator
- Skill DAG with parallel groups
- Three-layer Reflect validation (schema, coherence, confidence)
- Loop control with clarification short-circuit
- Mem0 / local memory adapter for user / session / agent scopes

### 8.2 What Changes

| Phase     | Change                                                                                                                                                                          |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| OBSERVE   | Inputs now include: active sector pack manifest, security band classification of every ingested element, PII-stripped data only, client engagement metadata (week #, decision gate position) |
| PLAN      | Planner respects: security mode (M1/M2/M3) — restricts which skills can call LLM; sector pack rules — selects sector-specific skills; engagement-week constraints — biases toward week-appropriate skills (e.g., diagnostic skills weeks 3–4, business case skills weeks 7–8) |
| ACT       | New skills available (see §9); LLM context built via `llm-context-builder` (B2-only, B3 tokenised); audit log emits per-skill data access record                                |
| REFLECT   | Confidence scoring replaced by assumption-register-driven ranges (P10/P50/P90); writes to engagement-scoped memory only (no cross-engagement leakage)                          |

### 8.3 Engagement-Scoped Memory

In v1.8, memory scopes were `user_id` / `session_id` / `agent_id`. In v2.0, the dominant scope is `engagement_id` — bounded to the specific 12-week engagement, destroyed at tear-down. Cross-engagement learning happens only through:

(a) **Anonymised aggregate metrics** (lever capture rates, benchmark gaps) stored in advisory's repository if and only if client consent obtained at SoW.

(b) **Sector pack version updates** — calibration adjustments roll forward through pack releases, not through live memory carry-over.

This is a deliberate constraint to avoid the perception or reality of one client's data informing another client's analysis.

---

## 9. Skills Catalog (Revised)

### 9.1 Carried Forward from v1.8

`spend-profiler`, `chart-builder`, `peer-benchmarker`, `internal-benchmarker`, `heuristic-analyzer`, `root-cause-analyzer`, `savings-modeler`, `value-bridge-calculator`, `data-validator`, `business-case-builder`, `analysis-synthesizer`, `executive-communication`, `bva-analyzer`, `temporal-analyzer`, `payment-terms-optimizer`.

These remain functionally similar but are extended for INR / Indian taxonomy / sector-pack awareness. Specifications in v1.8 §6.3.1 carry forward with that overlay.

### 9.2 New Skills in v2.0

| Skill                              | Purpose                                                                                                                  | Output                                                                                              | When invoked                              |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------- | ----------------------------------------- |
| **`pii-stripper`**                 | Scan ingested files for PII (PAN, Aadhaar, names, salaries, customer data); strip B4 fields before storage                | Stripped working dataset + audit record of what was stripped                                        | Every file ingestion (mandatory)          |
| **`data-classifier`**              | Classify every ingested element into B1–B4 security band                                                                  | Classification map; drives downstream LLM access rules                                              | Every file ingestion (mandatory)          |
| **`llm-context-builder`**          | Build LLM-safe context for narrative skills: B2 summaries only, B3 entities tokenised, B4 excluded                       | Context payload conforming to security mode                                                         | Before any LLM-calling skill              |
| **`sector-pack-loader`**           | Load active sector pack(s); merge taxonomy, benchmarks, levers, KPIs into engine config                                  | Engine config snapshot for engagement                                                              | Engagement initialisation                 |
| **`indian-tax-optimizer`**         | Identify GST ITC leakage, RCM exposure, inverted duty refund, TDS reconciliation gaps, Sec 115BAA modelling             | List of tax-driven savings opportunities with cash flow + after-tax NPV                            | Always (when GL data present)             |
| **`peer-disclosure-miner`**        | Mine BSE/NSE filings, earnings call transcripts, BRSR disclosures, MCA21 filings of peer set                              | Structured peer cost intelligence: stated programmes, headcount actions, capex/opex commentary    | Sector benchmarking phase                 |
| **`brsr-cobenefit-calculator`**    | Map every initiative to BRSR principle; compute emissions / water / waste delta                                          | ESG co-benefit overlay per initiative                                                              | Post-business-case                        |
| **`value-to-shareholder-bridge`**  | Translate cost-out portfolio to bps EBITDA, ΔROCE, ΔEPS, ΔFCF, ΔMarket-cap                                                 | Shareholder-value bridge (see §10)                                                                 | Final synthesis                           |
| **`assumption-register`**          | Capture every named assumption per initiative; manage P10/P50/P90 ranges; track source attribution                       | Assumption register (queryable + exportable)                                                        | Continuous (across phases)                |
| **`scenario-modeler`**             | Single-variable sensitivity (FX, commodity, wage inflation, execution rate, timing)                                      | Scenario set with NPV / EBITDA bps under each scenario                                             | Pre-board readout                         |
| **`mor-pack-generator`**           | Auto-generate Monthly Operating Review pack from current pipeline state                                                  | .pptx + .xlsx tracker + .docx narrative for the month                                              | Monthly cadence post-engagement (or weekly during sprint) |
| **`audit-trail-exporter`**         | Export full audit log (data accesses, skill invocations, LLM calls) for client SIEM and Audit Committee                  | Append-only log in SIEM-compatible format                                                          | Continuous + on-demand                    |
| **`tear-down-executor`**           | Execute the §5.7 tear-down protocol; produce attestation                                                                  | Tear-down report + attestation                                                                     | Engagement end                            |

### 9.3 Skill DAG — New Default Composition for an Indian C-Suite Engagement

```
Group 0:  pii-stripper, data-classifier
Group 1:  spend-profiler (sector-aware), document-contextualizer
Group 2:  peer-benchmarker (CMIE/Capitaline-driven) | internal-benchmarker | heuristic-analyzer | peer-disclosure-miner
Group 3:  root-cause-analyzer
Group 4:  indian-tax-optimizer | bva-analyzer | temporal-analyzer | payment-terms-optimizer
Group 5:  savings-modeler (with assumption-register integration)
Group 6:  value-bridge-calculator
Group 7:  brsr-cobenefit-calculator | scenario-modeler
Group 8:  business-case-builder
Group 9:  value-to-shareholder-bridge
Group 10: analysis-synthesizer | executive-communication (LLM, M1/M2/M3-aware)
Group 11: mor-pack-generator | dashboard-builder
```

---

## 10. Value-to-Shareholder Bridge

### 10.1 Why This Section Exists

A board does not buy "₹1,200 Cr of NPV." A board buys "+180 bps EBITDA margin, +220 bps ROCE, ₹14/share EPS uplift, ₹12,000 Cr of equity-value creation at current multiple." Every number the asset surfaces upward must translate into the second framing. This skill (`value-to-shareholder-bridge`) sits at the top of the synthesis stack and is mandatory for the board readout.

### 10.2 The Bridge

For an initiative portfolio with gross savings G(t), cost-to-achieve C(t), and tax rate τ:

```
Net Savings (Year t)        = G(t) − C(t)
Pre-tax EBITDA Impact (t)   = Net Savings (t)                   [if all savings hit opex]
After-tax PAT Impact (t)    = Pre-tax EBITDA Impact (t) × (1 − τ)
EPS Accretion (t)           = After-tax PAT Impact (t) / Diluted Shares Outstanding
EBITDA Margin Impact (bps)  = (Pre-tax EBITDA Impact (t) / Revenue (t)) × 10,000
ROCE Impact (bps)           = (After-tax PAT Impact (t) / Capital Employed (t)) × 10,000   [approximation; full bridge in §10.3]
FCF Impact (t)              = After-tax PAT Impact (t) + Working Capital Release (t) − Maintenance Capex Adjustment (t)
Equity Value Impact         = After-tax PAT Impact (steady state) × Trailing P/E Multiple
                              + Working Capital Release × 1.0   [direct cash effect]
```

For each initiative, the bridge is computed at the **steady-state run rate** (typically Year 3), then phased over 1–3 years for the run-rate portion. One-time savings flow only to FCF and one-time PAT, not to steady-state ROCE / EPS.

### 10.3 Full ROCE Bridge

Cost-out interacts with capital employed for two reasons: (a) working capital release reduces capital employed; (b) some initiatives free up fixed asset capacity (real estate consolidation, plant utilisation lift). The full bridge:

```
ΔROCE (bps)  = [ΔEBITDA × (1−τ) / Capital Employed₀]
              − [Capital Employed₀ × (ΔWC + ΔFA) / Capital Employed₀²]
              ≈ [ΔEBIT × (1−τ) − ROCE₀ × ΔCapital Employed] / Capital Employed₀
```

The asset surfaces both the numerator effect (PAT uplift) and denominator effect (capital release) separately so the board can see both levers.

### 10.4 Macro Sensitivity Surface

Every shareholder-bridge output is accompanied by a 6-scenario surface (defaults; configurable per engagement):

| Scenario              | Variable shifted                    | Default shift                     |
| --------------------- | ----------------------------------- | --------------------------------- |
| Base                  | None                                | —                                 |
| INR depreciation      | INR/USD                             | +5% (depreciation)                |
| INR appreciation      | INR/USD                             | −5% (appreciation)                |
| Wage inflation high   | India services wage CAGR            | +200 bps over base                |
| Commodity spike       | Commodity index relevant to sector  | +15% (sector-specific definition)  |
| Execution slip        | Initiative timing                   | +6 months                         |

Each scenario shows ΔEBITDA bps and ΔEPS vs. base. The board deck includes the full surface; the one-page CFO brief shows only the base case with a footnote on sensitivity.

### 10.5 Worked Example (Illustrative — Indian Manufacturer, ₹25,000 Cr Revenue)

| Initiative                        | Gross Y3 (₹ Cr) | Cost-to-Achieve (₹ Cr) | Net Y3 (₹ Cr) | bps EBITDA | bps ROCE | EPS Δ (₹) |
| --------------------------------- | ---------------:| ----------------------:| -------------:| ----------:| --------:| ---------:|
| Energy mix → 35% renewable        | 320             | 60                     | 260           | 104        | 78       | 0.65      |
| Logistics modal shift (rail)      | 180             | 25                     | 155           | 62         | 47       | 0.39      |
| Vendor base rationalisation       | 145             | 40                     | 105           | 42         | 32       | 0.26      |
| Plant utilisation lift (OEE)      | 220             | 90                     | 130           | 52         | 65       | 0.33      |
| Maintenance shift (CBM)           | 95              | 35                     | 60            | 24         | 18       | 0.15      |
| Working capital — DPO extension   | one-time 380   | 15                     | 365 cash      | —          | 110*     | 0.04**    |
| **Portfolio total**               | **960 + 380**   | **265**                | **710 + 365** | **284**    | **350**  | **1.82**  |

*Capital release effect on ROCE; **Tax effect on opportunity cost of capital. Equity value impact at 22× trailing P/E ≈ ₹15,800 Cr.

### 10.6 What the Asset Won't Do

- It will not fabricate a P/E multiple. Multiple comes from client management or analyst consensus, manually entered.
- It will not project topline impact of cost-out (e.g. "this will let us invest in growth"). That is a separate strategic narrative.
- It will not adjust for behavioural / second-order effects (e.g., demand destruction from price increases enabled by cost cuts). Those are flagged but not modelled.

---

## 11. Methodology Rigor

### 11.1 The Assumption Register

Every initiative carries a structured assumption register. This is the single most important credibility artefact for the Audit Committee.

```yaml
initiative_id: ENERGY_MIX_RENEWABLE
title: Shift power mix to 35% renewable via group captive PPA
assumptions:
  - id: A1
    description: Solar PPA tariff achievable
    base_value: ₹3.20 / kWh
    range_p10_p90: [₹2.90, ₹3.60]
    source: 3 indicative quotes (solar developer 1, 2, 3) + Mercom Q1 2026 average
    last_validated: 2026-04-15
    owner: Procurement Lead
    sensitivity: high   # one of [low, medium, high]
    what_would_change_my_mind: |
      If 6+ months of L1 bidding fails to achieve <₹3.40/kWh,
      revisit by reducing target to 25% renewable.
  - id: A2
    description: Open access charges stable
    base_value: ₹1.10 / kWh (current)
    range_p10_p90: [₹1.00, ₹1.40]
    source: State regulatory commission tariff order, Mar 2026
    last_validated: 2026-03-30
    owner: Energy Manager
    sensitivity: high
    what_would_change_my_mind: |
      State regulatory order revising cross-subsidy surcharge by >25%
      would reduce captive economics; flag as immediate review trigger.
  ...
range_summary:
  net_savings_y3_p10: ₹190 Cr
  net_savings_y3_p50: ₹260 Cr
  net_savings_y3_p90: ₹320 Cr
```

The register is queryable, exportable to Excel, and the data backing every cell in the board deck links back to specific assumption IDs. The Audit Committee can pull the full register and challenge any line.

### 11.2 Constructing P10/P50/P90 Ranges

Five accepted methods, picked per assumption:

| Method                                | When to use                                 | Implementation                                        |
| ------------------------------------- | ------------------------------------------- | ----------------------------------------------------- |
| Three-point estimate                  | Subject-matter expert input                 | Direct elicitation; PERT distribution fit             |
| Historical variance                   | Time-series data available                  | ±1 std dev for P10/P90; mean for P50                  |
| Peer dispersion                       | Benchmark with multiple peers               | 10th/50th/90th percentile of peer set                 |
| Monte Carlo on input distributions    | Multiple correlated inputs                  | 10k iterations; report 10th/50th/90th of output       |
| Scenario weighting                    | Discrete future states                      | Probability-weighted scenario outputs                 |

The skill `assumption-register` defaults to peer dispersion when peer data exists; falls back to three-point estimate via SME elicitation; flags Monte Carlo as needed for top-5 initiatives.

### 11.3 Replacing the Mechanical Confidence Score

v1.8 used 0.5 / 0.75 / 0.9 multipliers. v2.0 retains the multiplier internally for backward compatibility but **does not surface it to the C-suite**. C-suite-facing outputs use:

- **P10 / P50 / P90** ranges (not point + multiplier)
- A **5-factor RAG status** per initiative — *Data quality* (R/A/G), *Benchmark relevance* (R/A/G), *Owner readiness* (R/A/G), *Execution complexity* (R/A/G), *Regulatory clearance* (R/A/G)
- Explicit *what-would-change-my-mind* statement per assumption

This replaces an opaque arithmetic confidence score with a structured, challengeable, qualitative + quantitative view.

### 11.4 Audit Trail per Number

Every number in any C-suite output traces back through:

```
Final number (e.g., "₹260 Cr Net Y3 from Energy Mix")
  → assumption_register entries (A1, A2, A3, ...)
    → input data references (file path, line range, row IDs)
      → ingestion log (who uploaded, when, classification band)
        → original source (system of record reference, e.g., SAP table KEKO line item)
```

The Audit Committee can demand any number → trace path within the live cost room. This is enforced by the `audit-trail-exporter` skill.

### 11.5 Independent Validation Hooks

For engagements requiring third-party validation (M&A, board-level commitments, debt covenants), the asset supports:

- **Read-only auditor access** — separate role with full read of data + assumption register, no write
- **Snapshot freeze** — point-in-time freeze of all numbers and assumptions for auditor review; subsequent changes versioned
- **Reconciliation report** — every committed savings number reconciled to GL or budget line at engagement end

---

## 12. Outputs & Deliverables

### 12.1 Output Hierarchy

The asset produces five outputs in a strict hierarchy. Higher items in the hierarchy summarise lower items; lower items provide the evidence base.

| # | Output                             | Audience                          | Format        | First produced       |
| - | ---------------------------------- | --------------------------------- | ------------- | -------------------- |
| 1 | One-page CFO Brief                 | Group CFO, Group CEO              | .pdf / .docx  | Week 4 (refreshed weekly) |
| 2 | Board Narrative Deck               | Board, Audit Committee            | .pptx          | Week 11             |
| 3 | Live Cost Room                     | Group CFO, CTO Lead, Functional Owners | Interactive HTML / web app | Week 4 onwards |
| 4 | PMO Toolkit (Initiative Tracker)   | Cost Transformation Office, PMO    | .xlsx + web tracker | Week 8           |
| 5 | MOR Pack                           | Monthly Operating Review attendees | .pptx + .xlsx  | Month-end Week 12 onwards |

### 12.2 One-Page CFO Brief

A single page, refreshed weekly from Week 4. Structure:

```
┌──────────────────────────────────────────────────────────────────────┐
│  [Client Logo]   COST DIAGNOSTIC — WEEK X                           │
├──────────────────────────────────────────────────────────────────────┤
│  Total Addressable Spend (₹ Cr):    [X,XXX]                         │
│  Identified Opportunities (₹ Cr):   [X,XXX]   →  P50 portfolio      │
│  Committed Initiatives (₹ Cr):      [X,XXX]   →  in pipeline        │
│  → EBITDA Impact (Steady State):    +XX bps                         │
│  → ROCE Impact (Steady State):      +XX bps                         │
│  → EPS Accretion (Y3):              ₹X.XX                           │
├──────────────────────────────────────────────────────────────────────┤
│  Top 5 Pools by Opportunity         Top 5 Initiatives by NPV        │
│  1. ____________ ₹___ Cr            1. ____________ ₹___ Cr P50    │
│  2. ____________ ₹___ Cr            2. ____________ ₹___ Cr P50    │
│  3. ____________ ₹___ Cr            3. ____________ ₹___ Cr P50    │
│  4. ____________ ₹___ Cr            4. ____________ ₹___ Cr P50    │
│  5. ____________ ₹___ Cr            5. ____________ ₹___ Cr P50    │
├──────────────────────────────────────────────────────────────────────┤
│  Decisions needed this week:        Risks / Watch items:            │
│  • _________________________        • _________________________     │
│  • _________________________        • _________________________     │
└──────────────────────────────────────────────────────────────────────┘
```

Auto-generated. CFO reads in 2 minutes; can be sent into a CEO 1:1 cold.

### 12.3 Board Narrative Deck (15 slides)

Standard slide order; auto-generated and editable by the engagement team:

| # | Slide                                                                 |
| - | --------------------------------------------------------------------- |
| 1 | Cover + executive summary (₹ commitment, EBITDA bps, ROCE bps)        |
| 2 | Why now — macro and competitive context                                |
| 3 | Approach and 12-week sprint summary                                    |
| 4 | Cost base — current state by pool, addressable / semi / locked split   |
| 5 | Peer position — vs. listed Indian peer set, P25/P50/P75                |
| 6 | Top opportunities heat-map — pool size × gap to peer                   |
| 7 | Initiative portfolio — 30–80 initiatives, grouped by lever            |
| 8 | Phasing curve — Y1 / Y2 / Y3 net savings                               |
| 9 | Value-to-shareholder bridge — bps EBITDA, ROCE, EPS, equity value     |
| 10| BRSR / ESG co-benefit overlay                                          |
| 11| Sensitivity surface — base + 6 macro scenarios                         |
| 12| Investment ask — cost-to-achieve, capex, internal capacity             |
| 13| Governance — PMO charter, MOR cadence, decision rights                 |
| 14| Risks and mitigations                                                   |
| 15| Decision asks from board (specific, named)                             |

Backup: detailed assumption register, top-5 initiative deep-dives, peer position by category.

### 12.4 Live Cost Room

A web-based interactive view (deployed in client VPC; accessed via SSO). Allows the CFO and team to:

- Filter the initiative portfolio by lever / category / business unit / owner / status
- Toggle between P10 / P50 / P90 views
- Run macro scenarios live (FX, commodity, wage)
- Drill from any number to assumption register
- Reject / accept / defer initiatives with audit trail
- Export current view to deck / Excel

Tech: served by the same backend as the asset; HTML + Chart.js + Vue or similar lightweight frontend; no new infrastructure dependency.

### 12.5 PMO Toolkit

| Component                          | Purpose                                                    |
| ---------------------------------- | ---------------------------------------------------------- |
| Initiative master tracker (.xlsx + web) | One row per initiative; status, owner, milestones, actuals |
| RACI matrix                         | Per initiative cluster                                      |
| Milestone calendar                  | Cross-initiative critical path                              |
| Risk and dependency log             | Live during execution                                       |
| Variance and FTC report             | Auto-generated weekly during sprint, monthly thereafter     |
| Initiative business case template (.docx) | Standardised one-pager per initiative for owner sign-off |

### 12.6 MOR Pack

Generated automatically by `mor-pack-generator` at month-end (or weekly during sprint). Standard structure:

| Section                            | Content                                                    |
| ---------------------------------- | ---------------------------------------------------------- |
| Headline                           | Run-rate savings vs. plan; YTD; YTG forecast               |
| Pipeline movement                  | Identified → Committed → In-flight → Realised waterfall    |
| At-risk register                   | Initiatives off-track with reason + recovery action        |
| Variance commentary                | Top variances with primary driver                          |
| Decisions and escalations          | Items requiring CFO / CEO / Board attention                |
| Value-to-shareholder snapshot      | bps EBITDA / ROCE delivered vs. plan                       |
| Audit trail confirmation            | Confirms log integrity; flags any control exceptions       |

Standard pack: 8–12 slides (.pptx) + 1 detail Excel + 1 one-pager (.docx). Distribution list configurable per client.

---

## 13. The 12-Week Playbook

### 13.1 Sprint Overview

| Week | Phase                                | Headline Activity                                         | Decision Gate            |
| ---- | ------------------------------------ | --------------------------------------------------------- | ------------------------ |
| 1    | Mobilise & data discovery            | Deploy asset; data room; hypothesis tree                  | Hypothesis sign-off      |
| 2    | Ingest & profile                     | Data ingestion, taxonomy mapping, pool sizing             | Cost base sign-off       |
| 3    | Peer + internal benchmarking         | CMIE / peer-disclosure mining; BU benchmarking            | —                        |
| 4    | Diagnostic synthesis                 | Heat-map; first CFO brief                                 | **Gate 1: Direction**    |
| 5    | Pool deep-dives (top 5)              | Root-cause for top 5 pools                                 | —                        |
| 6    | Pool deep-dives (next 5)             | Root-cause for next 5 pools                                | —                        |
| 7    | Initiative shaping                   | 30–80 initiatives drafted with named owners               | —                        |
| 8    | Business case build                  | NPV, P10/P50/P90, BRSR co-benefit                          | **Gate 2: Portfolio**    |
| 9    | Risk, sequencing, capital plan       | Phasing, dependencies, cost-to-achieve                    | —                        |
| 10   | Synthesis & narrative                | Board deck v1; sensitivity surface                        | **Gate 3: Narrative**    |
| 11   | Stress test, audit, board prep       | AC pre-read; Q&A prep                                     | —                        |
| 12   | Board readout + PMO/MOR stand-up     | Board commitment; PMO live; tear-down planning            | **Gate 4: Commitment**   |

### 13.2 Week-by-Week Detail

#### Week 1 — Mobilise & Data Discovery

| Day  | Activity                                                                                                     | Deliverable                          | Owner             |
| ---- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------ | ----------------- |
| 1    | Deploy asset in client VPC; InfoSec walkthrough; engagement charter signed                                    | Deployment confirmation              | Asset team        |
| 2    | Kickoff with CFO + Cost Transformation Lead; sponsor check-in cadence locked                                  | Charter + cadence document           | Engagement Mgr    |
| 3    | Data request list issued (FY-3 to current GL, vendor master, headcount, BU/cost centre, contracts, BRSR)      | Data request                         | Engagement Mgr    |
| 4    | Hypothesis tree workshop with CFO + functional heads                                                          | Hypothesis tree                      | Engagement Mgr    |
| 5    | Data room set up; PII stripper + data classifier dry-run                                                      | Working data room                    | Asset team        |

**Gate output (Friday Week 1):** signed-off hypothesis tree + data request acknowledgment.

#### Week 2 — Ingest & Profile

| Day  | Activity                                                                                                     | Deliverable                          | Owner             |
| ---- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------ | ----------------- |
| 1–2  | Spend file ingestion; taxonomy mapping (sector pack applied); >85% auto-classification target                | Classified spend cube                | Engagement analyst |
| 3    | Manual taxonomy override session with FP&A team                                                              | Confirmed taxonomy                   | Engagement analyst + Client FP&A |
| 4    | Document context ingestion (contracts, board notes, prior consultant reports)                                | Document corpus                      | Engagement analyst |
| 5    | Data quality report; cost base presented to CFO                                                              | DQ report + cost base                | Engagement Mgr    |

**Gate output (Friday Week 2):** signed-off cost base by pool, by BU.

#### Week 3 — Peer + Internal Benchmarking

| Day  | Activity                                                                                                     | Deliverable                          | Owner             |
| ---- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------ | ----------------- |
| 1–2  | Peer-benchmarker run (CMIE / Capitaline pull); peer-disclosure-miner run                                     | Peer position report                 | Engagement analyst |
| 3    | Internal benchmarker run (BU vs. BU)                                                                         | Internal variance report             | Engagement analyst |
| 4    | Heuristic comparison run (cost / employee, cost / unit, cost / branch)                                       | Heuristic ratio set                  | Engagement analyst |
| 5    | Indian-tax-optimizer run (GST ITC, RCM, TDS); BvA + temporal trend run                                       | Tax + FP&A overlay                   | Engagement analyst |

#### Week 4 — Diagnostic Synthesis

| Day  | Activity                                                                                                     | Deliverable                          | Owner             |
| ---- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------ | ----------------- |
| 1–2  | Root-cause-analyzer run for >P60 pools                                                                       | Root cause map                       | Engagement Mgr    |
| 3    | Value-bridge-calculator run; first sizing of opportunity                                                      | Value bridge v1                      | Engagement Mgr    |
| 4    | First one-page CFO brief produced; live cost room launched                                                   | CFO brief v1; live cost room URL     | Engagement Mgr    |
| 5    | **Gate 1 review with CFO + sponsor**                                                                          | Direction sign-off                   | Group CFO         |

**Gate 1 — Direction:** Group CFO confirms (a) hypothesis tree is right, (b) top-10 pools by opportunity are correct, (c) shortlist of pools to deep-dive in weeks 5–6, (d) named functional owners for each pool.

#### Weeks 5–6 — Pool Deep-Dives

For each of the top 10 pools, a 2–3 day deep-dive:

| Activity                                                                                                                          | Output                                                     |
| --------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| Workshop with functional owner + 1–2 SMEs                                                                                          | Pool diagnosis (current state, peer position, root causes) |
| Lever shortlisting (3–5 levers per pool from sector pack defaults + engagement-specific)                                           | Lever shortlist with rationale                              |
| Initial sizing per lever (P10/P50/P90 ranges via assumption register)                                                              | Sized lever set                                             |
| Owner identification per lever (named individual, not role)                                                                       | Owner-mapped portfolio                                      |
| Friday week 6: refreshed CFO brief                                                                                                 | CFO brief v2                                                |

#### Week 7 — Initiative Shaping

| Day  | Activity                                                                                                     | Deliverable                          | Owner             |
| ---- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------ | ----------------- |
| 1–3  | One-pager initiative business case per initiative (template-driven, 30–80 initiatives)                       | Initiative one-pagers                | Engagement analyst + Functional owners |
| 4    | Cross-initiative dependency map; conflict resolution (e.g., headcount lever in 3 initiatives)                | Dependency map                       | Engagement Mgr    |
| 5    | First-pass prioritisation matrix (NPV vs. complexity vs. owner readiness)                                    | Prioritisation matrix                | Engagement Mgr    |

#### Week 8 — Business Case Build

| Day  | Activity                                                                                                     | Deliverable                          | Owner             |
| ---- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------ | ----------------- |
| 1–2  | Savings-modeler run (phased, NPV, IRR); cost-to-achieve sized                                                | Modelled portfolio                   | Engagement analyst |
| 3    | Value-to-shareholder-bridge run                                                                              | Shareholder bridge v1                | Engagement analyst |
| 4    | BRSR co-benefit overlay                                                                                      | ESG overlay                          | Engagement analyst |
| 5    | **Gate 2 review with CFO + Cost Transformation Lead + functional heads**                                     | Portfolio commitment                 | Group CFO         |

**Gate 2 — Portfolio:** Sign-off on the 30–80 initiative portfolio, named owners, sequencing intent, and the headline number to be presented to the board.

#### Week 9 — Risk, Sequencing, Capital Plan

| Day  | Activity                                                                                                     | Deliverable                          | Owner             |
| ---- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------ | ----------------- |
| 1–2  | Phasing curve build; cost-to-achieve phasing; capital allocation profile                                     | 24-month phased plan                 | Engagement Mgr    |
| 3    | Risk register build (per initiative + portfolio level)                                                       | Risk register                        | Engagement Mgr    |
| 4    | Internal capacity / change-management load assessment                                                        | Capacity assessment                  | Engagement Mgr    |
| 5    | Refreshed CFO brief; preview of board narrative thread                                                       | CFO brief v3                         | Engagement Mgr    |

#### Week 10 — Synthesis & Narrative

| Day  | Activity                                                                                                     | Deliverable                          | Owner             |
| ---- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------ | ----------------- |
| 1    | Scenario-modeler run (6-scenario macro surface)                                                              | Sensitivity surface                  | Engagement analyst |
| 2–3  | Board deck v1 drafted (executive-communication skill + manual editing)                                       | Board deck v1                        | Engagement Mgr    |
| 4    | Internal QC by sector lead + senior partner                                                                  | QC sign-off                          | Sector Lead       |
| 5    | **Gate 3 review with CFO**                                                                                    | Narrative sign-off                   | Group CFO         |

**Gate 3 — Narrative:** Group CFO signs off on the board story arc, the headline numbers, the sensitivity ranges, and the specific decision asks of the board.

#### Week 11 — Stress Test, Audit, Board Prep

| Day  | Activity                                                                                                     | Deliverable                          | Owner             |
| ---- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------ | ----------------- |
| 1    | Audit Committee Chair pre-read with assumption register                                                      | AC pre-read confirmation             | Group CFO + AC Chair |
| 2    | Board pre-read circulation; Q&A prep document                                                                | Board pre-read + Q&A bank            | Engagement Mgr    |
| 3    | CFO and CEO rehearsal of deck                                                                                 | Rehearsal feedback incorporated      | Group CFO         |
| 4    | Final deck refinements; backup slides                                                                        | Final board deck                     | Engagement Mgr    |
| 5    | PMO toolkit handover begins; MOR cadence agreed                                                              | PMO toolkit installed                | Cost Transformation Lead |

#### Week 12 — Board Readout + PMO Stand-up

| Day  | Activity                                                                                                     | Deliverable                          | Owner             |
| ---- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------ | ----------------- |
| 1    | Board readout                                                                                                 | Board commitment                     | Group CFO + CEO   |
| 2    | First MOR pack generated (baseline)                                                                          | MOR pack v0                          | Asset team + PMO  |
| 3    | PMO charter signed; ownership matrix locked                                                                  | PMO live                             | Cost Transformation Lead |
| 4    | Tear-down dry-run; data exfiltration to client                                                               | Exfiltration confirmation            | Asset team        |
| 5    | **Gate 4: Commitment** — engagement closeout; tear-down protocol initiated; optional 90-day support agreed   | Closeout deck + tear-down plan       | Engagement Partner |

**Gate 4 — Commitment:** Board confirms the portfolio, capital ask, governance, and reporting cadence. Asset team initiates §5.7 tear-down.

### 13.3 RACI Summary

| Activity cluster                          | R                   | A                  | C                                          | I                                |
| ----------------------------------------- | ------------------- | ------------------ | ------------------------------------------ | -------------------------------- |
| Asset deployment & security               | Asset team          | Engagement Partner | Client InfoSec, DPO                         | CFO, Cost Transformation Lead   |
| Data ingestion & taxonomy                 | Engagement analyst  | Engagement Manager | Client FP&A team                           | CFO                              |
| Benchmarking                              | Engagement analyst  | Engagement Manager | Sector Lead                                 | CFO, Functional Owners          |
| Pool deep-dives                           | Engagement Manager  | Engagement Partner | Functional Owners, SMEs                     | CFO                              |
| Initiative shaping                        | Engagement Manager  | Engagement Partner | Functional Owners                           | CFO                              |
| Business case + portfolio                 | Engagement Manager  | Engagement Partner | CFO, Functional Owners                      | CEO, Audit Committee Chair       |
| Board narrative                           | Engagement Partner  | CFO                | Engagement Manager                          | CEO, Board                       |
| Tear-down                                 | Asset team          | Engagement Partner | Client InfoSec                              | CFO, DPO                         |

### 13.4 Capacity Assumption

A standard 12-week deployment for a ₹15,000–50,000 Cr revenue Indian major:

| Role                    | FTE on engagement | Rationale                                                  |
| ----------------------- | ----------------- | ---------------------------------------------------------- |
| Engagement Partner      | 0.25              | Sponsor-facing, board prep, quality                         |
| Sector Lead             | 0.20              | Sector benchmark calibration, deep-dive review              |
| Engagement Manager      | 1.0               | Day-to-day; client-facing                                   |
| Engagement Analyst (×2) | 2.0               | Asset operation, deep-dives, deliverable production         |
| Client CFO time         | 4–6 hours / week  | Decision gates + weekly check-in                            |
| Client Cost Transformation Lead | 0.5–1.0 FTE | Day-to-day client counterpart                               |
| Functional Owners       | 4–6 hours / pool  | Concentrated in deep-dive weeks 5–6                         |

Total external cost (typical): ~25–35% of a comparable 16–24 week non-AI-augmented engagement.

---

## 14. Technical Architecture (Secure-by-Design)

The v1.8 technical stack (FastAPI, Python 3.11+, pandas, openpyxl, Mem0 / local memory, OPAR orchestrator) is carried forward. This section describes only what is added or changed for v2.0.

### 14.1 Deployment Topology (Default — Client VPC, Mode A)

```
                Client Identity Provider (Okta / AAD / Ping)
                           │  SSO + MFA
                           ▼
   ┌────────────────────────────────────────────────────────────┐
   │              CLIENT VPC (AWS Mumbai / Hyd / Az India)       │
   │                                                              │
   │   ┌─────────────┐    ┌─────────────────┐   ┌────────────┐  │
   │   │ Web frontend │◄──►│ FastAPI orchest │◄─►│ PostgreSQL │  │
   │   │ (cost room)  │    │ + OPAR + skills │   │ (engagement│  │
   │   └─────────────┘    └────────┬────────┘   │ data)      │  │
   │                                │             └────────────┘  │
   │                                ▼                             │
   │                       ┌────────────────┐                     │
   │                       │ S3-equivalent  │                     │
   │                       │ (encrypted via │                     │
   │                       │  client KMS)   │                     │
   │                       └────────────────┘                     │
   │                                                              │
   │     Audit log → Client SIEM (Splunk / Sentinel / QRadar)    │
   └─────────────────────────┬───────────────────────────────────┘
                             │   TLS 1.3 + mTLS, allowlisted egress
                             ▼
                  ┌─────────────────────────────┐
                  │   Regional Managed LLM       │
                  │   (Bedrock Mumbai / Azure    │
                  │    Pune; zero retention)     │
                  │   ── Mode M2 only            │
                  └─────────────────────────────┘
```

In Modes M1 (determinism-first) and M3 (on-prem LLM), the egress to managed LLM is removed. In Mode B (on-prem appliance), the entire VPC moves into the client data centre.

### 14.2 New / Changed Components

| Component                       | Status     | Purpose                                                                                           |
| ------------------------------- | ---------- | ------------------------------------------------------------------------------------------------- |
| `pii-stripper` service          | New        | Inline at ingestion; regex + NER (spaCy or Presidio) based                                        |
| `data-classifier` service       | New        | B1–B4 classification; runs after PII stripper                                                     |
| `llm-context-builder` service   | New        | Builds B2-only context; tokenises B3; rejects any B4                                              |
| `sector-pack-loader` service    | New        | Mounts active sector pack(s) as engine config                                                     |
| `audit-trail-exporter`          | New        | Streams audit log to client SIEM in real time (CEF / LEEF / JSON)                                 |
| `tear-down-executor`            | New        | Idempotent infrastructure destruction; produces attestation                                       |
| Memory adapter                  | Changed    | New `engagement_id` scope; `mem0` configuration restricted to engagement-bounded run IDs           |
| Frontend                        | Changed    | Cost room interactive view; SSO integration; B2/B3 visual masking when role does not allow access |
| Deployment toolkit              | New        | Terraform modules (AWS, Azure), Ansible (on-prem), helm charts                                    |
| Security hardening guide        | New        | InfoSec-facing document; standard answers to ~80 InfoSec questions                                |

### 14.3 Pinned Dependencies — Additions

In addition to the v1.8 pinned set:

| Package          | Pinned Version | Purpose                                                |
| ---------------- | -------------- | ------------------------------------------------------ |
| presidio-analyzer| 2.2.x          | PII detection (Microsoft open-source)                  |
| presidio-anonymizer | 2.2.x       | PII tokenisation                                        |
| spacy            | 3.7.x          | NER for vendor / person name detection                 |
| boto3 / azure-identity | latest stable | LLM endpoint authentication                          |
| python-jose      | latest stable  | SSO token validation                                    |
| structlog        | latest stable  | Structured audit logging                                |

### 14.4 Performance & Concurrency

The v1.8 optimisations carry forward (vectorised ingestion, module-level caches, asyncio parallel Act, slim LLM payloads). New SLOs for v2.0:

| Metric                                              | Target                                                                  |
| --------------------------------------------------- | ----------------------------------------------------------------------- |
| Time from ingestion to spend cube                   | < 2 minutes for ≤100k spend lines                                       |
| Time from ingestion to value bridge v1              | < 15 minutes for 50k lines + standard sector pack                       |
| Cost room interactive response time                 | < 500 ms for filter / drill operations                                  |
| Audit log latency (event to SIEM)                   | < 5 seconds                                                             |
| LLM call latency (Mode M2, narrative skills only)   | < 10 seconds p95                                                        |
| Tear-down execution                                 | < 2 hours wall-clock                                                    |

### 14.5 Backup, Continuity, DR

For the duration of the 12-week engagement only:

- Daily encrypted backup of engagement DB to client S3 (client-managed key)
- Backup retention: 14 days during engagement; deleted at tear-down
- No cross-region replication unless client requests
- RPO: 24 hours; RTO: 8 hours
- DR is engagement-scoped — full restore from backup possible within RTO; no multi-region active/active

---

## 15. Success Metrics

### 15.1 Per-Engagement Metrics (the 12-week sprint)

| Metric                                              | Target                                                                  |
| --------------------------------------------------- | ----------------------------------------------------------------------- |
| Diagnostic completion within 12 weeks               | 100%                                                                    |
| Identified savings as % of addressable spend         | 8–15% (P50)                                                             |
| Conversion identified → committed by Week 8          | ≥ 60% of identified by ₹                                                |
| Board commitment achieved at Gate 4                  | ≥ 80% of presented portfolio                                            |
| Audit trail coverage                                 | 100% of board-deck numbers traceable to source                          |
| InfoSec sign-off time (deployment to go-live)        | < 10 working days for ≥ 80% of clients                                  |
| Tear-down attestation completed within 7 days        | 100%                                                                    |
| Functional owner satisfaction (NPS proxy)             | ≥ +30 from interviewed owners                                           |
| Group CFO satisfaction                               | ≥ 4.5 / 5 on engagement closeout                                        |

### 15.2 Asset-Level Metrics (across deployments)

| Metric                                              | Target                                                                  |
| --------------------------------------------------- | ----------------------------------------------------------------------- |
| Number of engagements per year                       | 8–12 per ₹2 Cr investment in asset evolution                            |
| Sector pack coverage                                 | All listed sectors with material engagement potential                    |
| Time-to-value reduction vs. baseline                 | ≥ 40% (16-week classical → 12-week with asset)                           |
| Cost-to-deliver reduction vs. baseline               | ≥ 50%                                                                   |
| Engagement repeat rate (90-day support attach)        | ≥ 60%                                                                   |
| Repeat client rate within 24 months                   | ≥ 40% (different BU or refresh)                                          |
| Reference-able client count                          | Growing each quarter                                                     |
| Sector-pack regression suite pass rate               | 100% pre-release                                                        |
| Mean time between security findings                  | > 90 days; zero critical findings post-mitigation                       |

### 15.3 Lagging — 6 / 12 / 24 Months Post-Engagement

Tracked via optional 90-day support and longitudinal client check-ins:

| Metric                                              | Target                                                                  |
| --------------------------------------------------- | ----------------------------------------------------------------------- |
| Realised savings (cumulative) at 12 months           | ≥ 50% of committed                                                      |
| Realised savings at 24 months                        | ≥ 80% of committed                                                      |
| Initiative attrition rate                            | ≤ 25% by ₹                                                              |
| EBITDA margin movement attributable to programme    | Demonstrable and traceable                                               |
| Audit Committee citation of asset outputs           | Continued use in committee reviews                                       |

---

## 16. Risks & Mitigations

| #  | Risk                                                                                                  | Impact      | Mitigation                                                                                                                                |
| -- | ----------------------------------------------------------------------------------------------------- | ----------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| 1  | Client InfoSec rejects deployment due to LLM data flow concerns                                       | Engagement-killing | Default Mode M1 (determinism-first) for sensitive sectors; pre-engagement InfoSec briefing; sector-specific reference architectures        |
| 2  | Benchmark data licensing not in place at client (CMIE, CRISIL)                                        | Schedule slip | Pre-engagement check; advisory firm holds umbrella licences; fallback to MCA21 + BSE/NSE free data                                         |
| 3  | Client data quality below ingestion threshold (DQ < 0.6)                                              | Schedule slip | Pre-engagement data readiness assessment; 1-week buffer in plan; client-side data clean-up resource named                                 |
| 4  | Sector pack does not exist for client (niche sector)                                                  | Quality risk | Conglomerate-default pack as fallback; 5–8 day pack-build effort budgeted before engagement                                               |
| 5  | LLM model deprecation or pricing change disrupts asset                                                | Mid-term    | Multi-LLM abstraction layer; quarterly review; ability to fall back to Mode M1 indefinitely                                                |
| 6  | Initiative owners disengage post-Gate 2 — committed savings stall                                     | Realisation | Functional owner named at Gate 1, signed 1-pager at Gate 2; PMO charter mandates owner accountability through 90-day support              |
| 7  | Audit Committee challenges P10/P50/P90 ranges as too wide / too narrow                                | Credibility | Methodology disclosure built into board pack; assumption register exposed at AC pre-read; methodology backed by accepted practice         |
| 8  | Regulatory shift (DPDP rules, GST changes) mid-engagement                                             | Quality risk | Indian regulatory layer reviewed quarterly; engagement-week 1 includes regulatory snapshot; material shifts trigger Gate decision         |
| 9  | Data leakage event during or after engagement                                                         | Reputational, legal | Defence-in-depth controls (§5.6); cyber insurance; CERT-In playbook; tear-down attestation; quarterly third-party audit                   |
| 10 | Client refuses tear-down (wants asset to continue running)                                            | Commercial / governance | Default contract clause; if client wants continuation, separate licensed extension with renewed InfoSec review                              |
| 11 | Asset team rotation mid-engagement                                                                    | Quality risk | Engagement docs are first-class artefacts (not consultant tribal knowledge); onboarding guide allows mid-engagement substitution           |
| 12 | Dependency on a single advisory partner skews the asset to one firm's IP                              | Strategic   | Asset is modular; sector packs and skills are versioned and portable; not bound to any single consulting methodology                        |
| 13 | Cross-engagement memory (consent-based aggregates) violates a client's interpretation of confidentiality | Legal       | Aggregate consent option default-OFF; opt-in only; aggregates are ≥5-client-anonymised before any internal use                            |
| 14 | LLM hallucination in narrative output (e.g., fabricated peer quote)                                   | Credibility | LLM outputs are validated against source data (faithfulness judge from v1.7 eval framework); all peer quotes traced to source filing       |
| 15 | Group CFO turnover during engagement                                                                  | Sponsor risk | Engagement charter signed by both CFO and CEO; CEO briefing document maintained; can pause and re-engage with new CFO                     |

---

## 17. Appendices

### 17.A — Standard Taxonomy with India Extensions

The v1.8 25-category taxonomy is retained as the spine. Extensions per India context:

| Extension                                | Purpose                                                                      |
| ---------------------------------------- | ---------------------------------------------------------------------------- |
| Power → split into grid / captive / open access / renewable | India-specific energy structure                                             |
| Logistics → split into road / rail / coastal / air         | Modal-shift lever availability                                              |
| Real estate → split into metro / tier-2 / tier-3 / SEZ / STPI / GIFT | Cost arbitrage and tax incentive cells                                      |
| People costs → split into on-roll / off-roll / contract / GIC-shared | Statutory + flexibility levers                                              |
| Procurement → indirect tax overlay (GST ITC eligible / ineligible / RCM) | Tax-driven savings discoverable                                             |
| Banking & finance charges → bank charges / treasury / hedge cost / forex losses | Treasury optimisation                                                       |
| CSR / regulatory → discrete category (not addressable)     | Visibility without confusion                                                |
| Related-party transactions → discrete band                 | Conglomerate handling                                                       |

Sector packs add further sub-categories per their domain (see §6.4 BFSI, §6.5 Manufacturing).

### 17.B — Sector Pack Build Effort

Default time and effort to build a new sector pack from template:

| Activity                                           | Effort (person-days) |
| -------------------------------------------------- | -------------------- |
| Sector taxonomy extension                           | 1–2                  |
| Sector benchmark source identification & connector | 1–2                  |
| Sector lever library (3–5 levers, defaults)         | 1                    |
| Regulatory layer document                           | 0.5                  |
| KPI pack + deck template                            | 0.5–1                |
| Peer set + sample deep-dive                        | 0.5                  |
| Internal review by sector lead                     | 0.5                  |
| **Total**                                          | **5–8**              |

### 17.C — Glossary

| Term                                | Definition                                                                                                  |
| ----------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| OPAR                                | Observe → Plan → Act → Reflect; the engine's agentic loop                                                   |
| Sector pack                          | Plug-in module with sector-specific taxonomy, benchmarks, levers, regulation, KPIs                          |
| B1–B4                                | Security data classification bands: Public, Confidential, Restricted, PII/Regulated                        |
| M1–M3                                | LLM data-flow modes: Determinism-first, Regional managed LLM, On-prem LLM                                   |
| P10 / P50 / P90                      | 10th / 50th / 90th percentile estimate of an outcome under defined assumption ranges                         |
| Cost-to-Achieve                       | One-time and recurring spend required to capture a savings initiative                                       |
| FTC                                  | Forecast to Complete — projected realisation of an in-flight initiative based on actuals run-rate           |
| MOR                                  | Monthly Operating Review                                                                                    |
| Run-rate vs. one-time                 | Sustained annualised vs. single-period savings classification                                                |
| BRSR                                 | Business Responsibility & Sustainability Reporting (SEBI mandate, top 1,000 listed)                         |
| ITC                                  | Input Tax Credit (under GST)                                                                                |
| Ind AS                                | Indian Accounting Standards (IFRS-converged)                                                                |
| MCA21 / AOC-4                         | Ministry of Corporate Affairs filing system / annual financial filing form                                  |
| CMIE                                 | Centre for Monitoring Indian Economy (Prowess database)                                                     |

### 17.D — Security Architecture One-Pager (referenced from §5.8)

```
┌────────────────────────────────────────────────────────────────────┐
│  CLIENT PERIMETER (VPC / on-prem / air-gapped)                     │
│                                                                     │
│  Ingestion ──► PII Stripper ──► Data Classifier ──► Engagement DB  │
│   (B1-B4)        (B4 stripped)     (B1-B4 tagged)    (encrypted)   │
│                                                                     │
│                            │                                        │
│                            ▼                                        │
│                   Skills Engine (OPAR)                              │
│                            │                                        │
│            ┌───────────────┼───────────────┐                       │
│            │               │               │                        │
│      Determ. only      LLM context        Audit log                │
│      (always)          builder            (always)                  │
│                       (B2 only,                                     │
│                        B3 tokens)                                   │
│                            │                                        │
│                            ▼                                        │
│                    [Mode M2: Regional LLM]                          │
│                    Bedrock Mumbai / Azure India                     │
│                    Zero data retention                              │
│                                                                     │
│   Client SIEM ◄──────────── Audit log stream                       │
│   Client KMS ─────► All data at rest encrypted with client key     │
│                                                                     │
│   At T+0 (engagement end): all compute, storage, backups destroyed │
│   Attestation signed by Engagement Partner + Client InfoSec         │
└────────────────────────────────────────────────────────────────────┘
```

### 17.E — Data Request List (Standard, Customisable per Sector)

Standard pre-engagement data request, issued Day 3 of Week 1:

1. **GL extract** — last 36 months, line-item level, with `gl_code`, `cost_center`, `vendor`, `description`, `amount`, `currency`, `period`, `business_unit`, `geo`
2. **Vendor master** — full vendor list with category mapping if available, contracts > ₹1 Cr in value
3. **Headcount data** — by BU / function / location / band (no PII; aggregated counts and grades)
4. **Budget vs. Actuals** — last 24 months, monthly granularity
5. **Capex roster** — last 36 months, FY-current commitment view
6. **BRSR disclosure** — most recent filed report
7. **Annual Report + 10-K equivalents (AOC-4)** — last 3 years for each material entity
8. **Prior cost programmes** — any consultant reports, internal audit reports of cost programmes from last 3 years
9. **Treasury policies + hedge book summary** — for FX-relevant analysis
10. **Working capital aging** — DPO, DSO, DIO trends; debtors and creditors aging
11. **Sector-pack-specific items** — e.g., for Mfg: power consumption per plant, OEE data; for BFSI: branch P&L, channel mix; for Pharma: USFDA filings, plant compliance status

### 17.F — Sample Initiative One-Pager Template (for Functional Owners)

```
INITIATIVE: ____________________________________________________
ID: __________________   Pool: ________________   Lever: ______________
OWNER: __________________________________________________________

CURRENT STATE
  Spend (FY): ₹_____ Cr   |   Peer position: __ percentile
  Trigger: _________________________________________________________

PROPOSED CHANGE (3–5 lines)
  ___________________________________________________________________
  ___________________________________________________________________

EXPECTED IMPACT
  Y1: ₹___ Cr net   |   Y2: ₹___ Cr net   |   Y3: ₹___ Cr net (run rate)
  P10: ₹___ Cr   |   P50: ₹___ Cr   |   P90: ₹___ Cr
  Cost-to-achieve: ₹___ Cr   |   Payback: __ months
  EBITDA bps impact (Y3): __ bps   |   ROCE bps impact: __ bps

KEY ASSUMPTIONS (top 3, with source)
  A1: _______________________________________________________________
  A2: _______________________________________________________________
  A3: _______________________________________________________________

RISKS & DEPENDENCIES
  • _________________________________________________________________
  • _________________________________________________________________

MILESTONES (next 6 months)
  M1 (date): _______________________________________________________
  M2 (date): _______________________________________________________
  M3 (date): _______________________________________________________

OWNER CONFIRMATION
  Name: _____________________  Signature: _________________  Date: ___
```

### 17.G — Open Questions for v2.0

| # | Question                                                                                                                              | Owner                  | Blocking? |
| - | ------------------------------------------------------------------------------------------------------------------------------------- | ---------------------- | --------- |
| 1 | What is the default umbrella licensing posture for CMIE / CRISIL across engagements?                                                  | Asset Lead + Legal      | Yes       |
| 2 | Which advisory firm (or independent entity) owns the asset; what is the IP and commercial structure?                                   | Asset Lead              | Yes       |
| 3 | Which 4–5 sector packs are built first beyond BFSI and Manufacturing, based on pipeline?                                              | Asset Lead + Sales      | No        |
| 4 | For Mode M2, which managed LLM (Bedrock vs. Azure OpenAI vs. dedicated Anthropic India endpoint) is the default? Per sector defaults? | Asset Lead + InfoSec    | Yes       |
| 5 | Does the asset offer a self-service "lite" deployment for mid-cap clients (₹2,000–10,000 Cr)?                                        | Asset Lead + Commercial | No        |
| 6 | What is the SLA / commercial structure for the 90-day post-sprint support?                                                            | Asset Lead + Commercial | No        |
| 7 | Is consent-based aggregate metric retention valuable enough commercially to justify the contracting overhead?                         | Asset Lead              | No        |

### 17.H — Carry-Forward References

- v1.8 PRD §6 Technical Architecture, §7 Value Lever Framework, §10 Timeline & Phasing — referenced wherever this v2.0 document does not re-specify.
- OPAR Loop Specification v1.0 §1–§4 (Observe / Plan / Act / Reflect detail) — referenced in §8 of this document.
- FP&A Enhancement Plan v1.0 §1 (root-cause-analyzer, savings-modeler, pipeline-tracker), §2 (cost behaviour classification, benchmark source metadata, double-counting prevention), §6 (Mem0 schema), §7 (benchmark data strategy) — incorporated and extended in this v2.0 document.

---

*OpEx Intelligence Platform — Product Requirements Document v2.0 | Pallav Chaturvedi | May 2026*
