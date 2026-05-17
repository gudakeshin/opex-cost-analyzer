# OpEx Intelligence Platform — Frequently Asked Questions

**Last Updated:** May 2026 | **Version:** 3.0

---

## Product & Business Questions

### What problem does OpEx Intelligence solve?

**Problem:** Traditional cost optimization takes weeks or months (consulting engagement → data gathering → analysis → recommendations). Large enterprises struggle to identify cost-reduction opportunities across complex spend landscapes (100k–20M+ transactions).

**Solution:** OpEx Intelligence automates cost analysis in hours via an agentic OPAR loop (Observe-Plan-Act-Reflect), combining spend profiling, peer benchmarking, industry-specific levers, and financial modeling. Output: board-ready business case with quantified initiatives, phasing, and risk.

**See Also:** Executive Summary, § 1A (Use Cases)

---

### How long is a typical engagement?

**Standard:** 12 weeks from data upload to deliverables.

- **Weeks 1–4:** Spend discovery, peer benchmarking, anomaly identification
- **Weeks 5–8:** Value lever identification, business case development, scenario modeling
- **Weeks 9–11:** CFO review, initiative refinement
- **Week 12:** Final delivery (board deck, cost room, MOR pack), knowledge transfer, tear-down prep

**Post-Engagement:** T + 12 months, calibration cycle (realised vs. planned, lever range updates).

**See Also:** Appendix C (Engagement Lifecycle)

---

### What industries does the platform cover?

**11 Complete Sector Packs:**
1. BFSI (Banking, Financial Services, Insurance)
2. Manufacturing (Diversified, automotive, heavy equipment)
3. IT/ITeS (IT services, IT-enabled services, software)
4. FMCG (Fast-moving consumer goods, retail)
5. Pharma & Life Sciences (Pharma, biotech, CROs)
6. Energy & Utilities (Power, gas, water)
7. Insurance (General insurance, health, specialty)
8. Retail (Organized retail, e-commerce)
9. Telecom & Infrastructure (Telecom, tower companies)
10. PSU/CPSE (Public sector, state enterprises)
11. Conglomerate (Multi-business groups)

**Plus 30+ universal levers** applicable across all industries.

**Platform automatically detects industry** from spend signals (category concentration, keyword scanning) or documents uploaded.

**See Also:** § 8 (Sector Pack Architecture)

---

### What data formats does the platform accept?

**Formats:** CSV, Excel (XLS/XLSX), PDF (embedded spend tables), JSON

**Required Fields:**
- Supplier name
- Spend amount
- Category (or GL code)
- Spend date

**Optional But Recommended:**
- Subcategory, Business unit, Cost center, GL code
- Contract expiry, Payment terms, Related-party flag
- Currency, GST treatment, Lease treatment

**Processing:** Data validated, normalized to NormalizedSpendLine schema, classified for sensitivity (B1–B4), then profiled.

**See Also:** § 7 (Data Model), § 6 (Security)

---

### How much does it cost?

**Engagement Model:** Custom pricing based on:
- Annual spend under analysis (₹50 Cr–₹5000 Cr+)
- Scale tier (mid-cap ≤100k lines, large-cap ≤5M, conglomerate >5M)
- Deployment option (cloud vs. on-prem)
- LLM mode (M1 no LLM, M2 cloud, M3 on-prem)

**Infrastructure Cost:** ~₹1.5–3 Lakh/month for cloud (AWS/Azure), lower for on-prem.

**Contact:** Sales team for quote.

---

### Does the platform integrate with my ERP?

**Current:** Platform accepts CSV/Excel exports from any ERP (SAP, Oracle, NetSuite, etc.).

**Planned (v2.2):** Native connectors for SAP OData, Oracle EBS, NetSuite REST.

**Workaround:** Export spend from ERP monthly; upload to platform.

**See Also:** § 2 (System Overview), Appendix B (File Organization)

---

## Security & Compliance Questions

### How does the platform protect sensitive data?

**Multi-Layer Security:**

1. **PII Detection** — Presidio + spaCy + Indian-name NER (≥99.2% recall)
2. **Data Classification** — B1 (Public) → B4 (Restricted/PII)
3. **Band Enforcement** — B4 quarantined; B1–B3 flow through with LLM mode checks
4. **Encryption** — AES-256 at rest (KMS-backed), TLS 1.3 in transit
5. **Audit Log** — SHA-256 hash chain; streamed to client SIEM within 60 seconds

**Data Never Leaves Engagement:**
- After 12-week engagement, all client data deleted (except audit log narrative, archived for compliance)
- Zero-residual attestation signed (proof of deletion)

**See Also:** § 6 (Security Architecture), Appendix C (Tear-Down)

---

### What is data classification (B1–B4)?

| Band | Level | Examples | LLM Access |
|------|-------|----------|-----------|
| **B1** | Public | Aggregated metrics, peer benchmarks | All modes (M1/M2/M3) |
| **B2** | Internal | Company spend totals, non-sensitive categories | M2/M3 only (cloud/on-prem) |
| **B3** | Confidential | Sensitive suppliers, cost details, customer IDs | Tokenized only (M2/M3) |
| **B4** | Restricted/PII | Personal data, account numbers, medical info | NO LLM (quarantine) |

**Automatic:** Platform detects and classifies on upload. Re-classifies at every skill output boundary.

**See Also:** § 6 (Security Architecture)

---

### Can the platform run fully on-prem (no cloud)?

**Yes.** M3 (on-prem) deployment mode:
- Ollama (Llama 2, Mistral, etc.) runs in client data centre
- No data egress to cloud
- Client controls LLM model updates
- Higher latency than cloud (1–5s vs. 500ms–2s)

**Trade-Off:** Full privacy + control vs. slower inference.

**See Also:** § 5 (LLM Providers), § 13 (Deployment Architectures)

---

### Is the platform SOC 2 certified?

**Current:** Not yet (in progress for 2026 H2).

**Compliance Ready:** Architecture supports HIPAA, GDPR, RBI IT Risk framework, GST/IT Act compliance.

**Audit:** Available for supervised code review (source code escrow arrangement possible).

**See Also:** docs/security/infosec_faq.md (82 security Q&A)

---

### What happens to my data after the engagement ends?

**Post-Engagement (Tear-Down):**

1. **Delete:** Infrastructure, memory, backups (9 steps)
2. **Archive:** Audit log narrative + assumptions register exported to client (encrypted)
3. **Verify:** DLP check on consultant laptops (no local copies)
4. **Attest:** Signed attestation: "zero_residual_confirmed"

**No Retention:** Platform deletes all engagement data. Client SIEM owns audit log long-term.

**See Also:** Appendix C (Tear-Down Checklist), § 13 (Deployment)

---

## Technical Questions

### How does the OPAR loop work?

**Four Phases:**

1. **Observe** — Classify intent (upload_data? benchmark? value_bridge?), load memory context, assess data quality
2. **Plan** — Build skill DAG (AI-powered dependency resolution), preview execution plan to user
3. **Act** — Auto-detect industry, run skill groups in parallel, surface degradation banners
4. **Reflect** — Validate outputs, quality gate (AssumptionQualityScore ≥ 0.65), tag narrative provenance, decide CONTINUE or DONE

**Loop Can Pivot:** If quality gate fails, Plan regenerates before retrying Act.

**See Also:** § 3 (OPAR Loop), § 4 (Skill DAG)

---

### What are the 26 skills?

**Organized in 8 groups:**

| Group | Skills | Count |
|-------|--------|-------|
| **0 — Security** | pii-stripper, data-classifier, llm-context-builder | 3 |
| **1 — Data** | data-validator, spend-profiler | 2 |
| **2 — Benchmarking** | peer-benchmarker, internal-benchmarker, peer-disclosure-miner | 3 |
| **3 — Analysis** | heuristic-analyzer, root-cause-analyzer, bva-analyzer, temporal-analyzer | 4 |
| **4 — Tax** | indian-tax-optimizer, brsr-cobenefit-calculator | 2 |
| **5 — Financial** | savings-modeler, payment-terms-optimizer, assumption-register, scenario-modeler | 4 |
| **6 — Value** | value-bridge-calculator, value-to-shareholder-bridge | 2 |
| **7 — Outputs** | chart-builder, document-contextualizer, export-formatter | 3 |

**Group 0 runs first; Groups 1–7 follow dependency graph. Groups can run in parallel within constraints.**

**See Also:** § 4 (Skill DAG)

---

### What are "sector packs"?

**Definition:** Industry-specific libraries of cost-reduction levers.

**Contents (per pack):**
- 8–9 sector-specific levers (e.g., "MRO consolidation" for manufacturing)
- P10/P50/P90 savings ranges
- Sustainability score (long-term viability)
- Bounce-back risk (behavioral reversion likelihood)
- Phasing curves (realization timeline)
- Condition precedents (required preconditions)

**Example:** Manufacturing pack includes levers like "predictive maintenance", "MRO consolidation", "energy audit", "factory automation".

**Universal Levers:** 30+ cross-industry levers (contract renegotiation, demand management, supplier consolidation, etc.) apply to all packs.

**See Also:** § 8 (Sector Pack Architecture)

---

### How does "addressability" work?

**Goal:** Calculate how much of each spend line can actually be optimized.

**Four Dimensions:**
1. **Regulatory Override** — Hard floors (GST, PF, statutory audit) can't be negotiated
2. **Contract Window** — Time until flexibility (long contract → low addressability)
3. **Switching Cost** — Cost to switch suppliers (IT 12%, Telecom 8%, etc.)
4. **Cost Behaviour** — Fixed costs can't be reduced via volume levers

**Calculation:** Start with spend amount → apply dimensions sequentially → result = addressable amount

**Example:** ₹100 IT spend, fixed cost, 12-month contract:
- Behaviour: ₹100 × 0% (fixed) = ₹100
- Regulatory: No override
- Contract: ₹100 × 0.40 (12 months) = ₹40
- Switching: ₹40 − (12% × ₹40) = ₹35.20 **addressable**

**See Also:** § 9 (Addressability Engine)

---

### What are the 7 sensitivity scenarios?

| Scenario | Execution | Timeline | Purpose |
|----------|-----------|----------|---------|
| Conservative | 60% | Normal | Downside case |
| Base | 80% | Normal (phased) | Planning target |
| Accelerated | 90% | 1.5× speed | Upside case |
| Delayed | 80% | 4× timeline | Risk case |
| Partial | 80% | Normal | Only top-3 categories |
| Volume Growth | 80% | Normal | Spend pool scales with revenue/headcount |
| Bounce-Back | 80% | + reversion at month 30 | Behavioral reversion risk (sustainability < 0.50) |

**Use:** Board presentation (show range of outcomes), engagement scope (pick risk tolerance).

**See Also:** § 11 (Sensitivity Analysis)

---

### What's the difference between M1, M2, M3 LLM modes?

| Mode | Technology | Data Residency | Latency | Use Case |
|------|-----------|-----------------|---------|----------|
| **M1** | Deterministic (no LLM) | N/A | < 100 ms | BFSI, Healthcare (no LLM allowed); fast path |
| **M2** | Claude (cloud India) | ap-south-1 / centralindia | 500 ms–2 s | Most engagements; balance of capability + security |
| **M3** | Ollama (on-prem) | Client data centre | 1–5 s | Highly regulated; maximum privacy + control |

**Data Band Enforcement:** B4 (PII) → NO LLM in any mode. B3 (Confidential) → tokenized only. B1/B2 → all modes OK.

**See Also:** § 5 (LLM Providers)

---

### Can I customize the platform?

**Yes.** Skill-based architecture allows extending without core changes:
- Add new skills (Python modules + SKILL.md spec)
- Add sector packs (sector_levers.json + regulatory_layer.md)
- Modify skill contracts (validation schemas in Pydantic)

**No Changes Needed To:** OPAR orchestrator, skill DAG planner, quality gates, audit log.

**See Also:** § 4 (Skill DAG), Appendix B (File Organization)

---

### What's the performance SLA?

**By Scale Tier:**

| Tier | Ingestion | Filter (Cost-Room) |
|------|-----------|-------------------|
| Mid-Cap (≤100k) | < 1 s | < 500 ms |
| Large-Cap (≤5M) | < 30 s | < 200 ms |
| Conglomerate (>5M) | < 120 s | < 100 ms |

**Achieved Via:**
- Mid-cap: In-memory pandas
- Large-cap: DuckDB + Parquet + Redis cache
- Conglomerate: Parquet chunks + Spark/Polars + Redis cache

**See Also:** § 12 (Scale Tiers)

---

## Deployment Questions

### Which cloud regions are supported?

**Recommended:**
- **AWS:** ap-south-1 (Mumbai, primary)
- **Azure:** centralindia (Pune, primary)

**Why India:** RBI data residency requirements, GST/tax compliance, latency.

**Other Regions:** Possible but not officially supported. Contact sales for non-India deployments.

**On-Prem:** Client data centre (any location). M3 mode (Ollama) ensures no egress.

**See Also:** § 13 (Deployment Architectures)

---

### How do I deploy to AWS/Azure/on-prem?

**Recommended:** Use Terraform (Infrastructure as Code) in `/deploy/terraform/`.

**AWS:**
```bash
cd deploy/terraform/aws
terraform apply -var="region=ap-south-1"
```

**Azure:**
```bash
cd deploy/terraform/azure
terraform apply -var="location=centralindia"
```

**On-Prem:**
```bash
cd deploy/ansible
ansible-playbook site.yml -i inventory/production.ini
```

**See Also:** DEPLOYMENT-CHECKLIST.md, § 13 (Deployment Architectures)

---

### What's the RTO/RPO?

**RTO (Recovery Time Objective):** 30 minutes
- Restart ECS task (AWS), Container Apps (Azure), or systemd service (on-prem)

**RPO (Recovery Point Objective):** 24 hours
- Daily encrypted backups; 14-day retention

**Disaster Recovery:** Full environment can be re-provisioned via Terraform in < 30 min.

---

### How do I monitor the platform in production?

**AWS:** CloudWatch Logs + CloudWatch Alarms (CPU, disk, error rate).

**Azure:** Application Insights + Azure Monitor Alerts.

**On-Prem:** Prometheus + Grafana (with AlertManager).

**SIEM Integration:** Audit log streamed to client SIEM in CEF/LEEF format within 60 seconds.

**See Also:** DEPLOYMENT-CHECKLIST.md (post-deployment validation)

---

## Support & Next Steps

### Where can I find more detailed information?

| Topic | Resource |
|-------|----------|
| **Architecture Overview** | Main architecture.md document (§ 1–13) |
| **Security Deep-Dive** | docs/security/hardening_guide.md, infosec_faq.md |
| **Deployment** | DEPLOYMENT-CHECKLIST.md, § 13 (Deployment Architectures) |
| **Use Cases** | § 1A (Common Workflows) in main architecture.md |
| **Glossary** | End of architecture.md + GLOSSARY.md (expanded) |
| **File Organization** | Appendix B (File Organization) |
| **Engagement Lifecycle** | Appendix C (Engagement Lifecycle & Calibration) |

---

### How do I get started?

**Step 1:** Read the Executive Summary + Use Cases (§ 1A) — 15 minutes

**Step 2:** Choose deployment path (AWS/Azure/on-prem) — reference DEPLOYMENT-CHECKLIST.md

**Step 3:** Contact sales for pilot engagement — typical timeline 12 weeks

**Step 4:** Schedule architecture deep-dive with engineering team

---

### Who do I contact for questions?

- **Product / Licensing:** [sales@opex-intelligence.io]
- **Technical / Deployment:** [support@opex-intelligence.io]
- **Security / Compliance:** [security@opex-intelligence.io]
- **Emergency Support:** [emergency@opex-intelligence.io]

---

**Document Version:** 3.0 | **Last Updated:** May 2026

For the latest version, visit: https://docs.opex-intelligence.io/architecture/
