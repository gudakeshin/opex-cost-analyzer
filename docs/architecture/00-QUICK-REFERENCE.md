# OpEx Intelligence Platform — Quick Reference Guide

**Last Updated:** May 2026 | **Version:** 3.0

---

## Reading Paths

### **Path A: Executive (5 minutes)**
For business decision-makers evaluating the platform.

1. **Executive Summary** (main doc) — Platform overview, value props, India-first design
2. **Use Cases** (§ 1A) — Four concrete workflows showing business impact
3. **Section Summaries** — Key takeaways from each technical section

**Time: 5 min** | **Outcome:** Understand platform value and whether it fits your needs

---

### **Path B: Product / Business Analyst (30 minutes)**
For those owning product strategy, partnerships, or business outcomes.

1. **Executive Summary** (main doc)
2. **§ 1: System Context & Stakeholders** — Who uses it, what they do
3. **§ 1A: Common Workflows** — Real scenarios (spend discovery, value quantification, compliance)
4. **§ 3: OPAR Loop** — How the platform orchestrates analysis
5. **§ 4: Skill DAG** — The 26 capabilities and their organization
6. **§ 6: Security Architecture Summary** — Data protection at a glance
7. **Appendix C: Engagement Lifecycle** — 12-week cycle and calibration

**Time: 30 min** | **Outcome:** Understand business capabilities, user workflows, security posture

---

### **Path C: Architect / Engineer / Security Team (2–3 hours)**
For technical deep-dives, implementation planning, or security audits.

**Read the full document in order:**
1. Executive Summary & How to Read This Document
2. § 1–13 (all technical sections)
3. All Appendices (stack, files, lifecycle, glossary)

**Focus Areas by Role:**
- **System Architects:** § 2, 3, 4, 13 (system design, OPAR, skills, deployment)
- **Engineers:** § 2, 3, 4, 5, Appendix B (file organization)
- **Security/Compliance:** § 6, 13 (security, deployment, tear-down), Appendix C (calibration)
- **Data Engineers:** § 7, 9, 12 (data model, addressability, scale tiers)
- **Financial Modelers:** § 8, 10, 11 (sector packs, lever intelligence, scenarios)

**Time: 2–3 hours** | **Outcome:** Complete technical understanding, implementation-ready

---

## Key Statistics

- **Platform Size:** 26 skills across 8 groups
- **Sector Coverage:** 11 industry-specific packs (all complete)
- **Universal Levers:** 30+ cross-industry opportunities
- **Scale Tiers:** Mid-Cap (≤100k lines), Large-Cap (≤5M), Conglomerate (≤20M)
- **Deployment Options:** 3 (AWS ap-south-1, Azure centralindia, on-prem)
- **Data Sensitivity Bands:** 4 (B1–B4, with automatic classification)
- **LLM Modes:** 3 (M1 deterministic, M2 cloud India, M3 on-prem)
- **Sensitivity Scenarios:** 7 (conservative, base, accelerated, delayed, partial, volume growth, bounce-back)
- **Engagement Cycle:** 12 weeks

---

## Critical Concepts (Glossary Snapshot)

| Term | Definition |
|------|-----------|
| **OPAR Loop** | Observe-Plan-Act-Reflect agentic cycle; orchestrates iterative cost analysis |
| **Sector Pack** | Industry-specific library of 8–9 levers (11 packs for 11 sectors) |
| **Addressability** | 4-dimensional model: regulatory override, contract window, switching cost, cost behaviour |
| **Lever Intelligence** | Engine that auto-detects industry, resolves eligible levers, scores by relevance |
| **B1–B4 Classification** | Data sensitivity bands; B4=PII quarantined, B1–B3 proceed with band enforcement |
| **Gate-2 Promotion** | Quality threshold (AssumptionQualityScore ≥ 0.65) for CFO review |
| **Sustainability Score** | Long-term viability of a lever (0–1); drives bounce-back risk assessment |
| **M1/M2/M3 Modes** | LLM deployment: deterministic, cloud India region, on-prem Ollama |
| **Tear-Down** | Post-engagement 9-step data deletion process; zero-residual attestation |

---

## Section Map

| Section | Topic | Key Diagram | Read Time |
|---------|-------|-------------|-----------|
| Exec Summary | Value props, design principles | — | 3 min |
| **1** | System Context | Fig. 1 — C4 Context | 5 min |
| **1A** | Use Cases (4 workflows) | — | 10 min |
| **2** | Functional Blocks | Fig. 2 — C4 Container | 8 min |
| **3** | OPAR Loop | Fig. 3 — Flowchart | 10 min |
| **4** | Skill DAG (26 skills) | Fig. 4 — Dependency graph | 8 min |
| **5** | LLM Modes (M1/M2/M3) | Fig. 5 — Mode selection | 7 min |
| **6** | Security Architecture | Fig. 6 — Classification → Audit | 10 min |
| **7** | Data Model | Fig. 7 — Class diagram | 8 min |
| **8** | Sector Packs (11 packs) | Fig. 8 — Pack + calibration | 10 min |
| **9** | Addressability (4-dim) | Fig. 9 — Dimension flow | 10 min |
| **10** | Lever Intelligence | Fig. 10 — Inference + scoring | 12 min |
| **11** | Sensitivity (7 scenarios) | Fig. 11 — Scenario matrix | 5 min |
| **12** | Scale Tiers | Fig. 12 — Tier selection | 6 min |
| **13** | Deployment | Fig. 13 — AWS/Azure/on-prem | 8 min |
| **Appendices** | Stack, files, lifecycle, glossary | — | As needed |

---

## Common Questions Answered

**Q: Can the platform run on [my cloud provider]?**
A: Yes—AWS ap-south-1, Azure centralindia, or on-prem Ansible. See § 13 (Deployment Architectures).

**Q: What data sensitivity does the platform handle?**
A: B1–B4 classification with automatic PII detection (≥99.2% recall). B4 (PII) is quarantined; B1–B3 flow through with band enforcement. See § 6 (Security).

**Q: How does the platform choose LLM providers?**
A: Three modes: M1 (no LLM, rule-based), M2 (cloud India, zero-retention), M3 (on-prem Ollama). See § 5 (LLM Providers).

**Q: How many industries does the platform support?**
A: 11 complete sector packs + 30+ universal levers. Auto-detects industry from spend signals. See § 8 (Sector Packs) & § 10 (Lever Intelligence).

**Q: What's the typical engagement timeline?**
A: 12 weeks from data upload to board-ready business case. Calibration cycle at T+12M. See Appendix C (Engagement Lifecycle).

**Q: How does the platform protect sensitive data?**
A: Multi-layer: PII detection → B1–B4 classification → band enforcement → audit log (SHA-256 hash chain → SIEM). See § 6 (Security).

**Q: Can the platform be customized?**
A: Yes—skill-based architecture allows extending with new capabilities. No core OPAR changes needed. See § 4 (Skill DAG) & Appendix B (File Organization).

---

## Navigation Tips

1. **Use the Table of Contents** in the main document to jump to specific sections
2. **Each section has a "Why This Matters" intro** — read it first to decide if you need full depth
3. **Diagrams are numbered (Fig. 1–13)** — refer back to them for visual understanding
4. **"Key Insight" callout boxes** highlight critical points
5. **"Section Summary" sections** recap key takeaways
6. **Glossary at end** defines all technical terms

---

## Feedback & Questions

This documentation is designed for external stakeholder sharing. If you have questions or suggestions:
1. Check the Glossary first (end of main doc)
2. Review the Use Cases (§ 1A) for similar scenarios
3. Reach out to the product team with specific questions

---

**Document Scope:** Architecture, design, deployment. For implementation details, see code comments and README.md.
