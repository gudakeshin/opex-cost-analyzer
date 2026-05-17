# OpEx Intelligence Platform Documentation — Master Index

**Version:** 3.0 | **Last Updated:** May 2026 | **Status:** External Distribution Ready

---

## Documentation Structure

This documentation package contains everything stakeholders need to understand, evaluate, deploy, and operate the OpEx Intelligence Platform. Choose your entry point based on your role.

---

## Quick Links

### **For Business Decision-Makers (5 minutes)**
Start here if you're evaluating the platform's business value.

1. **[00-QUICK-REFERENCE.md](00-QUICK-REFERENCE.md)** — Navigation guide, key statistics, reading paths
2. **[architecture.md](../architecture.md)** — Executive Summary (read first 300 words)
3. **[architecture.md § 1A](../architecture.md#1a-common-workflows--how-opex-intelligence-solves-real-problems)** — Four concrete workflows
4. **[FAQ.md](FAQ.md)** — Product & Business section

**Outcome:** Understand value prop, industries covered, typical timeline, costs.

---

### **For Product / Business Analysts (30 minutes)**
Start here if you're evaluating features, partnerships, or competitive positioning.

1. **[00-QUICK-REFERENCE.md](00-QUICK-REFERENCE.md)** — Reading paths, section map
2. **[architecture.md](../architecture.md)** — Sections 1–6 (System Context through Security)
3. **[architecture.md § 1A](../architecture.md#1a-common-workflows--how-opex-intelligence-solves-real-problems)** — Use cases
4. **[FAQ.md](FAQ.md)** — Product, Business, and Security sections

**Outcome:** Understand architecture, capabilities, security posture, and how the platform enables workflows.

---

### **For Technical Architects / Engineers (2–3 hours)**
Start here if you're designing, implementing, or integrating the platform.

1. **[architecture.md](../architecture.md)** — Full document (all sections 1–13 + appendices)
2. **[DEPLOYMENT-CHECKLIST.md](DEPLOYMENT-CHECKLIST.md)** — Infrastructure setup and validation
3. **[FAQ.md](FAQ.md)** — Technical section
4. **[00-QUICK-REFERENCE.md](00-QUICK-REFERENCE.md)** — Glossary snapshot

**Outcome:** Complete technical understanding, deployment-ready, implementation guidance.

---

### **For Security / Compliance Teams (45 minutes)**
Start here if you're assessing data protection, regulatory compliance, or audit requirements.

1. **[architecture.md § 6](../architecture.md#6-security-architecture)** — Security Architecture (detailed)
2. **docs/security/hardening_guide.md** — Deployment hardening checklist (11 sections)
3. **docs/security/infosec_faq.md** — 82 security Q&A (data, auth, LLM, infrastructure, compliance, incident response)
4. **[architecture.md § 13](../architecture.md#13-deployment-architectures)** — Deployment (data residency, encryption, audit log)
5. **[architecture.md Appendix C](../architecture.md#appendix-c-engagement-lifecycle--calibration)** — Tear-down procedure (9 steps)

**Outcome:** Understand data protection, encryption, audit logging, compliance readiness, tear-down procedure.

---

### **For DevOps / Operations (1 hour)**
Start here if you're deploying and operating the platform.

1. **[DEPLOYMENT-CHECKLIST.md](DEPLOYMENT-CHECKLIST.md)** — Pre-deployment through operations
2. **[architecture.md § 13](../architecture.md#13-deployment-architectures)** — Three deployment options (AWS, Azure, on-prem)
3. **[00-QUICK-REFERENCE.md](00-QUICK-REFERENCE.md)** — Key statistics, navigation
4. **[FAQ.md](FAQ.md)** — Deployment and Troubleshooting sections

**Outcome:** Deployment-ready, operational runbooks, troubleshooting guide.

---

## Document Map

| Document | Audience | Purpose | Read Time |
|----------|----------|---------|-----------|
| **[architecture.md](../architecture.md)** | All | Complete technical & business reference; 16 sections + 4 appendices | 2–3 hrs |
| **[00-QUICK-REFERENCE.md](00-QUICK-REFERENCE.md)** | All | Navigation guide, reading paths, key stats, glossary snapshot | 5 min |
| **[DEPLOYMENT-CHECKLIST.md](DEPLOYMENT-CHECKLIST.md)** | Ops / Architects | Step-by-step deployment validation; pre-deployment through operations | 30 min |
| **[FAQ.md](FAQ.md)** | All | Answers to 40+ common questions, organized by role | 20 min |
| **docs/security/hardening_guide.md** | Security / Ops | 11-section deployment hardening checklist | 20 min |
| **docs/security/infosec_faq.md** | Security / Compliance | 82 security questions & answers | 30 min |

---

## Architecture Documentation Sections

### **Main Document (architecture.md)**

| Section | Topic | Key Diagram | Type |
|---------|-------|-------------|------|
| **Intro** | Executive Summary, How to Read, Table of Contents | — | Guide |
| **1** | System Context & Stakeholders | Fig. 1 (C4 Context) | Architecture |
| **1A** | Common Workflows (4 use cases) | — | Business |
| **2** | System Overview (functional blocks) | Fig. 2 (C4 Container) | Architecture |
| **3** | OPAR Loop (orchestration) | Fig. 3 (Flowchart) | Architecture |
| **4** | Skill DAG (26 skills in 8 groups) | Fig. 4 (Dependency graph) | Architecture |
| **5** | LLM Providers (M1/M2/M3 modes) | Fig. 5 (Mode selection) | Architecture |
| **6** | Security Architecture | Fig. 6 (Classification → Audit) | Security |
| **7** | Data Model | Fig. 7 (Class diagram) | Data |
| **8** | Sector Packs (11 full packs) | Fig. 8 (Pack + calibration) | Business |
| **9** | Addressability Engine (4-dimension) | Fig. 9 (Dimension flow) | Financial |
| **10** | Lever Intelligence Engine | Fig. 10 (Inference + scoring) | Financial |
| **11** | Sensitivity Analysis (7 scenarios) | Fig. 11 (Scenario matrix) | Financial |
| **12** | Scale Tiers | Fig. 12 (Tier selection) | Infrastructure |
| **13** | Deployment Architectures | Fig. 13 (AWS/Azure/on-prem) | Infrastructure |
| **Appendix A** | Technology Stack Reference | Table | Reference |
| **Appendix B** | File Organization & Key Modules | Table | Reference |
| **Appendix C** | Engagement Lifecycle & Calibration | Timeline | Process |
| **Glossary** | Technical Terms (20+) | — | Reference |

---

## Key Concepts by Topic

### **Business & Value**
- Executive Summary (platform value, India-first design, key features)
- § 1A: Common Workflows (4 concrete examples)
- § 8: Sector Packs (11 industries, 30+ universal levers)
- Appendix C: Engagement Lifecycle (12-week cycle, calibration)

### **Architecture & Design**
- § 2: System Overview (13 functional blocks)
- § 3: OPAR Loop (4-phase orchestration)
- § 4: Skill DAG (26 skills in dependency order)
- § 13: Deployment (AWS, Azure, on-prem, Kubernetes)

### **Data & Analytics**
- § 7: Data Model (NormalizedSpendLine, SessionAnalysisState, Initiative)
- § 9: Addressability Engine (4-dimension model)
- § 10: Lever Intelligence Engine (industry inference, eligibility scoring)
- § 11: Sensitivity Analysis (7 scenarios, bounce-back risk)
- § 12: Scale Tiers (100k–20M+ lines)

### **Security & Compliance**
- § 6: Security Architecture (PII detection, B1–B4 classification, audit log)
- § 5: LLM Modes (M1/M2/M3, data band enforcement)
- docs/security/hardening_guide.md (deployment hardening)
- docs/security/infosec_faq.md (82 security Q&A)
- Appendix C: Tear-Down Procedure (9 steps, zero-residual attestation)

### **Deployment & Operations**
- § 13: Deployment Architectures (AWS, Azure, on-prem, K8s)
- DEPLOYMENT-CHECKLIST.md (pre-deployment through operations)
- docs/security/hardening_guide.md (security hardening)

---

## Diagrams & Visualizations

**13 Mermaid diagrams** illustrating architecture, data flow, and workflows:

- **Fig. 1** — System Context (users, LLMs, benchmarks, SIEM, KMS)
- **Fig. 2** — Container Diagram (13 functional blocks)
- **Fig. 3** — OPAR Loop (4 phases + replanner + quality gate + provenance)
- **Fig. 4** — Skill DAG (8 groups, dependency graph)
- **Fig. 5** — LLM Mode Selection (M1/M2/M3 + data band enforcement)
- **Fig. 6** — Security Architecture (PII detection → classification → band enforcement → audit log)
- **Fig. 7** — Data Model (class diagram, 4 core classes)
- **Fig. 8** — Sector Pack Architecture (11 packs + universal + calibration loop)
- **Fig. 9** — Addressability Engine (4 sequential dimensions)
- **Fig. 10** — Lever Intelligence Engine (industry inference + eligibility scoring)
- **Fig. 11** — Sensitivity Scenarios (7 scenarios, bounce-back risk)
- **Fig. 12** — Scale Tiers (mid-cap/large-cap/conglomerate + cache strategy)
- **Fig. 13** — Deployment Architectures (AWS/Azure/on-prem/K8s)

---

## Glossary

**Full glossary** at end of architecture.md; snapshot in 00-QUICK-REFERENCE.md.

**20+ key terms defined:**
- OPAR Loop, Sector Pack, Addressability Engine, Lever Intelligence, B1–B4 Classification
- Gate-2 Promotion, Sustainability Score, M1/M2/M3 Modes, Skill Engine, Tear-Down
- DAG, PII, SIEM/CEF/LEEF, Phasing Curve, Bounce-Back Risk, Cost Room, Initiative
- Calibration Pipeline, and more...

---

## Rendering & Format

**Format:** Markdown (.md) with Mermaid diagrams embedded

**Rendering:**
- ✓ GitHub (diagrams render inline)
- ✓ GitLab (diagrams render inline)
- ✓ Pandoc (convert to PDF/DOCX)
- ✓ VS Code (with markdown preview)
- ✓ Web browsers (via markdown renderers)

**PDF Export (Recommended for Distribution):**
```bash
# Using Pandoc
pandoc architecture.md -o architecture.pdf \
  --from markdown \
  --toc \
  --number-sections \
  --pdf-engine=xelatex

# Result: Professional 50–60 page PDF, table of contents, cross-references
```

---

## Document Status & Readiness

✓ **Content Complete** — All 16 sections + 4 appendices written
✓ **Diagrams Verified** — 13 Mermaid diagrams render correctly
✓ **Cross-References Checked** — All § links and glossary references accurate
✓ **Audience-Focused** — Multiple reading paths (executive, analyst, architect, security, ops)
✓ **Professional Polish** — Executive summary, use cases, callout boxes, section summaries
✓ **External Distribution Ready** — Suitable for client handoff, investor reviews, board presentations

---

## How to Use This Documentation

### **Scenario 1: Quick Pitch (5 min)**
→ Share **Executive Summary** (main doc) + **Use Cases** (§ 1A)

### **Scenario 2: Product Evaluation (1 hour)**
→ Send **architecture.md** + **00-QUICK-REFERENCE.md** + **FAQ.md**
→ Recommend: Path A or B reading (5–30 min)

### **Scenario 3: Security Assessment (45 min)**
→ Send **§ 6** (Security Architecture) + **docs/security/** files + **Appendix C** (Tear-Down)
→ Available for architecture review call

### **Scenario 4: Deployment Planning (2+ hours)**
→ Send **DEPLOYMENT-CHECKLIST.md** + **§ 13** + **full architecture.md**
→ Schedule deep-dive with engineering team

### **Scenario 5: Board Presentation**
→ Extract **Executive Summary** + **Use Cases** (§ 1A) + **4 key diagrams** (Fig. 1, 3, 8, 11)
→ Create 15-slide deck emphasizing speed, India-first design, security

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| **3.0** | May 2026 | Restructured for external distribution; added executive summary, use cases, quick reference, deployment checklist, FAQ |
| 2.1 | Mar 2026 | Added FP&A enhancements (BvA, trends, payment-terms, sensitivity) |
| 2.0 | Jan 2026 | Added sector packs, calibration pipeline, bounce-back risk |
| 1.0 | Oct 2025 | Initial architecture documentation |

---

## Next Steps

### **For Evaluators:**
1. Read Executive Summary + Use Cases (15 min)
2. Skim 00-QUICK-REFERENCE.md (5 min)
3. Review FAQ.md sections relevant to your role (10–20 min)
4. Schedule 30-min product walkthrough

### **For Implementers:**
1. Review full architecture.md (2–3 hours)
2. Follow DEPLOYMENT-CHECKLIST.md for your deployment target
3. Schedule architecture deep-dive with engineering
4. Plan 4-week implementation timeline

### **For Security / Compliance:**
1. Review § 6 + docs/security/ files (45 min)
2. Schedule security deep-dive
3. Provide feedback on hardening requirements
4. Plan SOC 2 / compliance assessment

---

## Contact & Support

- **General Inquiries:** [sales@opex-intelligence.io]
- **Technical Questions:** [support@opex-intelligence.io]
- **Security Review:** [security@opex-intelligence.io]
- **Emergencies:** [emergency@opex-intelligence.io]

---

## License & Confidentiality

**© OpEx Intelligence 2026**

This documentation is provided for evaluation purposes. Unauthorized copying, distribution, or public disclosure without written permission is prohibited. Contact sales for licensing terms.

---

**Documentation v3.0 — Professional, External Distribution Ready**

For the latest version and updates: https://docs.opex-intelligence.io/
