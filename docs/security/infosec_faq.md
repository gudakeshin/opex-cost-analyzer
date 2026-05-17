# OpEx Intelligence Platform — InfoSec FAQ (~80 Questions)

**Version:** 2.1  
**Audience:** Client CISO / InfoSec team reviewing the platform before engagement kickoff  
**Classification:** INTERNAL — share only under NDA with authorised client security personnel

---

## Section A — Data Classification & Handling (Q1–Q15)

**Q1. How is spend data classified when it enters the platform?**  
All ingested data is classified into one of four bands (B1–B4) by the `data-classifier` skill immediately at ingestion, before any storage or LLM access occurs. B1 = public-safe; B2 = internal; B3 = confidential (aggregate inference risk); B4 = restricted/PII.

**Q2. How is PII detected and handled?**  
A `pii-stripper` skill runs on every spend line using Microsoft Presidio + spaCy + an Indian-name NER overlay. Items flagged as B4 are quarantined — they are not passed to any LLM and are stored encrypted in a separate partition. Target recall ≥ 99.2% (validated on synthetic + anonymised Indian GL datasets before each release).

**Q3. What happens if a B4 item slips through PII detection?**  
Re-classification runs at every skill output boundary (not just at ingestion). If a derived field is later inferred to contain B4 content, it is re-quarantined and a security alert is appended to the immutable audit log.

**Q4. Does the platform store raw employee names or Aadhaar/PAN numbers?**  
No. The PII stripper replaces detected entities with tokens (e.g., `[PERSON_1]`, `[TAX_ID_1]`) before storage. Raw values are never written to disk or passed to an LLM.

**Q5. Where is spend data physically stored during the engagement?**  
Inside the client's VPC — specifically in the object storage bucket and local filesystem paths provisioned by the Terraform/Ansible deployment. No data leaves the client's environment except LLM prompts (see Q14).

**Q6. Is data stored encrypted at rest?**  
Yes. All files are encrypted using AES-256 with keys managed in the client's KMS (AWS KMS / Azure Key Vault / on-prem HSM). The platform never holds plaintext data outside of process memory during active computation.

**Q7. How are encryption keys managed?**  
The client's KMS holds the data encryption keys. The platform authenticates to KMS using a dedicated IAM role / managed identity with least-privilege access. Keys rotate annually (configurable). The platform never has access to the KMS master key.

**Q8. Is data encrypted in transit?**  
Yes. TLS 1.3 is enforced for all inter-service communication (API, Redis, object storage). TLS 1.2 minimum for external feeds (regulatory sources). The API endpoint is not exposed to the public internet.

**Q9. What data is retained after the engagement ends?**  
Nothing. The tear-down executor deletes: pack-lock files, memory scope, calibration artefacts, local backups. Audit logs are shipped to the client SIEM before deletion. IaC destroy removes all cloud resources. A zero-residual attestation is generated.

**Q10. How long is data retained during the engagement?**  
For the 12-week engagement duration + 14 days post close (to allow final outputs to be confirmed by the client). Daily backups are auto-expired after 14 days via S3/Blob lifecycle policy.

**Q11. Can the advisory firm's staff access client data outside the engagement VPC?**  
No. The platform is deployed inside the client VPC. Staff access the API via VPN/bastion only during the engagement. No data is copied to advisory firm infrastructure.

**Q12. Does the platform handle GST/financial data subject to income tax confidentiality?**  
Yes. All financial data is classified B2 or B3. Outputs that aggregate data to fewer than 5 supplier rows are automatically elevated to B3 (k-anonymity rule) and excluded from LLM context.

**Q13. Is the platform compliant with India's Digital Personal Data Protection Act (DPDPA) 2023?**  
The platform is designed to support DPDPA compliance: PII is detected and quarantined, data is retained only for the stated engagement period, tear-down generates deletion attestation. Formal DPDPA compliance assessment is the client's responsibility with their DPO.

**Q14. What data is sent to external LLM APIs?**  
Only B2-classified, PII-stripped, tokenised spend summaries and analytical prompts. Raw line-level data, supplier names, and any B3/B4 content are never included in LLM prompts. In M2 mode (Bedrock Mumbai / Azure Central India), data stays in India. In M1 mode (deterministic), no LLM is called at all.

**Q15. Does the platform use LLM training data from client inputs?**  
No. The platform uses Anthropic's API with zero-retention policy (Claude API commercial tier). Anthropic does not use API inputs for model training. In M2 Bedrock mode, AWS similarly provides no-training guarantees under the enterprise agreement.

---

## Section B — Authentication & Access Control (Q16–Q28)

**Q16. How do users authenticate to the platform?**  
Via SSO integration (Okta / Azure AD / Ping Identity) using SAML 2.0 or OIDC. Local accounts are not created. JWT tokens are validated on every API request.

**Q17. What roles are available?**  
Four base roles: `viewer` (read outputs only), `analyst` (upload + run analyses), `engagement_lead` (approve gates, accept/reject initiatives), `admin` (configure packs, manage engagement lifecycle). Role assignments are scoped to a single engagement.

**Q18. Is there multi-factor authentication (MFA)?**  
MFA is enforced by the client's SSO provider. The platform does not add a separate MFA layer — it relies on the SSO assertion. Clients using Okta or Azure AD with Conditional Access policies are covered.

**Q19. How are privileged operations (CFO override, Gate-2 bypass) controlled?**  
Privileged operations require a separate `engagement_lead` role claim in the JWT. Every privileged action is logged to the immutable audit trail with the user identity and timestamp. Time-bound elevation (24 hours) is enforced — permanent privilege escalation is not possible.

**Q20. Can a consultant access another client's engagement data?**  
No. All data and memory are scoped to `engagement_id`. JWT tokens include an `engagement_id` claim validated on every request. There is no cross-engagement data path.

**Q21. Is session management secure?**  
JWT tokens expire after 8 hours. Tokens are signed with RS256. Refresh tokens are not issued — users re-authenticate via SSO on expiry. Token revocation relies on SSO provider's session invalidation.

**Q22. How are API keys for external services (Anthropic, CMIE) stored?**  
In the client's secrets manager (AWS Secrets Manager / Azure Key Vault). Never in source code, environment files, or git history. Injected at runtime via IAM role/managed identity — the application process reads them on startup, not from disk.

**Q23. Is there a service account for automated processes (backups, reg watcher)?**  
Yes. A dedicated `opex-service` IAM role with minimal permissions: read/write to engagement S3 prefix only; Secrets Manager read for its own API key; no admin or cross-engagement access.

**Q24. How is the Redis cache access controlled?**  
Redis is deployed in a private subnet with a security group rule allowing only the ECS task security group. Redis AUTH password is stored in Secrets Manager and rotated per engagement.

**Q25. Are there audit logs for authentication events?**  
Yes. SSO login success/failure, JWT validation failure, and privilege escalation events are all logged to the immutable audit trail.

**Q26. What happens when a consultant's access is revoked?**  
Revoke the SSO user from the engagement group in the client's IdP. All in-flight JWT tokens expire within 8 hours (no active invalidation mechanism — if immediate revocation is needed, rotate the JWT signing key).

**Q27. Is the API protected against brute-force attacks?**  
Rate limiting is applied at the nginx / WAF layer: 100 req/min per authenticated user, 10 req/min per IP for unauthenticated endpoints. Login attempts are handled by the SSO provider which has its own lockout policy.

**Q28. Does the platform support RBAC at the initiative/lever level?**  
Pool-scoped RBAC allows functional owners to be assigned to specific initiative clusters. An analyst assigned to "Logistics" cluster cannot accept/reject initiatives in "IT Software" cluster. All scope assignments are logged.

---

## Section C — LLM Security (Q29–Q40)

**Q29. Which LLM providers are supported?**  
M1 (no LLM — deterministic rules only), M2 (AWS Bedrock ap-south-1, Azure OpenAI Central India, Anthropic API), M3 (on-prem Llama/Mistral via Ollama — zero external egress). The mode is set per engagement at kickoff.

**Q30. Can the LLM be prompted to reveal client data?**  
The `llm-context-builder` skill constructs a sanitised context containing only B2-classified, PII-stripped, aggregated data. The LLM receives no raw spend lines, no supplier names, and no B3/B4 content. Prompt injection via uploaded documents is mitigated by stripping executable content before passing to LLM.

**Q31. Is there a prompt injection risk from uploaded documents?**  
Uploaded documents (PDF, DOCX) are parsed as structured text only. Content that resembles LLM instructions (e.g., "ignore previous instructions") is flagged and excluded from LLM context by the `document-contextualizer` skill's sanitisation pass.

**Q32. Are LLM prompts logged?**  
Prompt metadata is logged (skill name, model mode, approximate token count, timestamp) but not the full prompt text. The audit log does not contain client data in readable form.

**Q33. Can the platform operate with no LLM at all?**  
Yes — M1 mode is fully deterministic. All 13 core analytical skills operate without LLM. Three skills degrade in M1 (peer-disclosure-miner, executive-communication, doc-contextualizer) and display a degradation banner in outputs.

**Q34. What is the data retention policy of the LLM providers?**  
Anthropic API: zero retention (no training use) under enterprise agreement. AWS Bedrock: no training use; data subject to AWS's in-region retention. Azure OpenAI: no training use; data stays in the selected Azure region. Clients must verify these terms match their DPA.

**Q35. Is the LLM output censored or filtered?**  
LLM outputs are passed through a post-processing filter that checks for: (a) hallucinated numerical figures inconsistent with input data (flagged, not removed), (b) any pattern matching a PII regex (redacted). Narrative provenance tags every sentence to its source data slice.

**Q36. Can the LLM be used to exfiltrate data?**  
The LLM API is called server-side. The API response is processed within the engagement VPC and is never returned directly to the user — it is incorporated into the structured output schema. Users see analyst-reviewed outputs, not raw LLM responses.

**Q37. Does the platform support air-gapped / offline LLM?**  
M3 mode supports Ollama-hosted Llama/Mistral. The Ollama server must be deployed within the client VPC. The platform sends prompts to the local Ollama endpoint — no internet egress for LLM calls.

**Q38. How is LLM model version pinned?**  
Each engagement locks the model version at kickoff in the narrative provenance store. If the provider updates the model mid-engagement, the locked version continues to be used via the provider's versioned model ID.

**Q39. What happens if the LLM generates factually incorrect content?**  
Narrative provenance tags identify the source data slice for every claim. The assumption register links each initiative's P10/P50/P90 to the data source (peer dispersion, historical, 3-point estimate). Users are expected to validate LLM-generated narratives against the source data before client delivery.

**Q40. Is the LLM provider subject to India's data localisation requirements?**  
Bedrock (ap-south-1) and Azure OpenAI (centralindia) process data within India. Anthropic's API routes through the US — use only for BFSI or sectors where cross-border transfer is prohibited if using Anthropic direct. M1 or M3 modes have zero external egress.

---

## Section D — Infrastructure & Deployment (Q41–Q55)

**Q41. Is the platform deployed in the client's own AWS/Azure account?**  
Yes. The Terraform module provisions all resources into the client's account using a dedicated IAM role. The advisory firm has no standing access to client cloud accounts.

**Q42. What cloud regions are supported?**  
AWS: ap-south-1 (Mumbai). Azure: centralindia (Pune). On-prem: any Linux x86_64 host. Deployment to regions outside India requires explicit client approval and DPA amendment.

**Q43. Is there a shared-tenancy risk between clients?**  
No. Each engagement deploys its own isolated VPC, its own S3/Blob bucket, its own KMS key, its own ECS cluster/Container App environment. There is no shared infrastructure between engagements.

**Q44. How is the deployment pipeline secured?**  
Terraform state is stored in a client-owned S3 bucket with versioning and KMS encryption. Terraform plan output is reviewed before apply. No CI/CD pipeline has write access to production — applies are run from the consultant's bastion with MFA.

**Q45. Is the Docker image signed and provenance-verified?**  
Images are signed using Docker Content Trust (DCT) or Cosign (if Sigstore is available). The image tag includes a SHA256 digest pinned in Helm values. Trivy scans for CRITICAL CVEs before deployment.

**Q46. How are OS-level patches applied during the engagement?**  
For ECS Fargate: base image is rebuilt weekly with the latest Python slim-bookworm patches; rolling deployment via ECS service update. For on-prem: `unattended-upgrades` is configured for security packages only; non-security updates require change advisory board approval.

**Q47. Is the platform resilient to availability zone failure?**  
AWS ECS service spans two AZs (ap-south-1a, ap-south-1b). For on-prem single-node deployments, systemd `Restart=always` ensures automatic restart within 5 seconds on process failure.

**Q48. What is the RTO/RPO for the platform?**  
RTO: 30 minutes (ECS service restart or on-prem systemd restart). RPO: 24 hours (daily backup to S3/Blob). These targets apply to the analytical platform itself — not to client's source systems.

**Q49. Is there a disaster recovery (DR) plan?**  
Daily encrypted backups to S3 (14-day retention, auto-expired). In a disaster scenario, Terraform apply into a new VPC using the backed-up state. Note: the 14-day backup window is engagement-scoped; no long-term DR is maintained post tear-down.

**Q50. How is the Redis cache protected?**  
Redis runs in a private subnet. AUTH password is required. TLS encryption is enabled for in-transit data (Redis 7.0+ TLS). `bind 127.0.0.1` on on-prem deployments. `maxmemory-policy allkeys-lru` prevents OOM crashes from becoming a DoS vector.

**Q51. Is there container escape hardening?**  
Containers run with `readOnlyRootFilesystem: true` (writable volumes mounted explicitly). `allowPrivilegeEscalation: false`. All Linux capabilities dropped. `seccomp` profile: `RuntimeDefault`. No privileged containers.

**Q52. Are Kubernetes RBAC policies enforced?**  
Yes. The opex service account has `get`, `list`, `watch` on its own namespace resources only. No cluster-admin or cross-namespace access. Network policies restrict pod-to-pod traffic to opex namespace.

**Q53. Is the Helm chart stored in a private registry?**  
Yes. The chart is hosted in the client's private OCI registry (ECR / ACR / Nexus). The `helm push` step uses a service account with write-once access — no delete permissions on published charts.

**Q54. How is the infrastructure tracked for tear-down?**  
All resources are tagged with `opex:engagement_id`. The `verify_cloud_tags` function queries the cloud provider's resource tag API after Terraform destroy and asserts zero resources remain with that tag. This result is included in the tear-down attestation.

**Q55. Can on-prem deployment operate completely offline (no internet)?**  
M1 + M3 (Ollama) mode with local Llama model can operate fully offline. Regulatory feed polling is disabled in offline mode. Peer benchmark data from licensed sources (CMIE, Capitaline) must be pre-loaded. Docker images must be pre-pulled and available in a local registry.

---

## Section E — Compliance & Governance (Q56–Q65)

**Q56. Is the platform ISO 27001 certified?**  
The platform itself is not certified — it is a consulting tool deployed per-engagement. The advisory firm's ISMS (ISO 27001 certified) governs how the platform is deployed and managed. Client should satisfy themselves that this scope covers their requirements.

**Q57. Is the platform SOC 2 Type II compliant?**  
Not independently assessed. The underlying cloud providers (AWS, Azure) are SOC 2 Type II certified. Clients requiring SOC 2 coverage for the platform itself should use M1 mode with on-prem deployment inside their own SOC 2 scope.

**Q58. Does the platform comply with RBI's IT Risk and Cyber Security Framework?**  
The platform is designed to align with: data localisation (ap-south-1/centralindia), audit trail requirements, access controls, and encryption at rest/transit. Formal RBI compliance is the client bank's responsibility — the advisory firm provides a RBI-mapping document on request.

**Q59. Is BRSR co-benefit reporting auditable?**  
BRSR co-benefit calculations are tagged with source data (spend lines, lever P50, BRSR principle mapping). The assumption register stores the methodology. Outputs include a BRSR section traceable to source data — suitable for internal audit review.

**Q60. How is the assumption register protected from tampering?**  
Assumption register entries are immutable once created — updates append new versions with a `modified_at` timestamp and `modified_by` identity. The original entry is retained. All modifications are logged to the audit trail.

**Q61. Is the platform's audit log admissible for regulatory review?**  
The audit log uses an append-only, hash-chained format. Each entry's hash is computed from the previous entry's hash + current event data (tamper-evidence). Logs are shipped to the client's SIEM in CEF/LEEF format for long-term retention by the client's compliance team.

**Q62. How does the platform handle related-party / conglomerate data under Ind AS disclosure requirements?**  
Spend lines flagged `related_party_flag=True` are tracked separately. Related-party aggregates are included in outputs with a disclosure note. The platform does not perform intercompany elimination automatically — this is flagged for analyst review.

**Q63. Is there a data processing agreement (DPA) template?**  
Yes — available from the engagement team. The DPA covers: data types processed, processing purposes, retention periods (engagement duration + 14 days), sub-processors (LLM provider, cloud provider), and deletion obligations.

**Q64. What is the engagement IP ownership policy?**  
Engagement outputs (analyses, business case, board deck) are the client's property. Platform code and sector packs are the advisory firm's IP, licensed for use during the engagement under the MSA. After tear-down, no copy of platform code remains on client systems.

**Q65. Is the platform assessed under CERT-In's incident reporting requirements?**  
The client is the CERT-In reportable entity. The platform provides audit logs and incident context to support the client's incident reporting obligations. A security incident playbook is available from the engagement team.

---

## Section F — Incident Response (Q66–Q75)

**Q66. What constitutes a security incident for this platform?**  
Any of: (a) suspected B4 data exposure to LLM, (b) unauthorised access to the engagement VPC, (c) audit log integrity failure, (d) data exfiltration attempt, (e) PII stripper recall failure on production dataset.

**Q67. What is the incident response process?**  
1. Detect (SIEM alert or manual observation) → 2. Contain (isolate affected ECS task / Redis / S3 bucket) → 3. Notify engagement lead + client CISO within 2 hours → 4. Preserve evidence (export audit log snapshot) → 5. Eradicate → 6. Recover → 7. Post-incident review within 5 business days.

**Q68. Who do I contact in case of a security incident?**  
Primary: engagement security lead (contact in engagement RACI). Secondary: platform security team at security@opex.internal. For critical incidents (B4 exposure, data breach): CISO-level escalation within 2 hours per engagement SLA.

**Q69. How are security patches deployed during an active engagement?**  
Critical CVEs (CVSS ≥ 9.0): patched within 24 hours via rolling deployment. High CVEs (CVSS 7.0–8.9): patched within 72 hours. Lower severity: bundled in weekly patch window. All patches require a change record in the engagement risk log.

**Q70. Is there a backup in case audit logs are corrupted?**  
Audit logs are shipped to client SIEM in near-real-time (within 60 seconds). If local logs are corrupted, SIEM retains the authoritative copy. The hash-chain verification detects corruption; a broken chain triggers an immediate alert.

**Q71. What happens if a sector pack is found to contain incorrect regulatory information?**  
A `SectorPackError` is raised on next regression test run. The pack is locked at its current version (no automatic update). The engagement lead is notified to review. The corrected pack version must pass regression tests before being used in active engagements.

**Q72. What is the process if a consultant laptop with cached data is lost or stolen?**  
Follow the DLP checklist from the tear-down executor output. Report to the engagement lead and client CISO immediately. Execute remote wipe of the device via the advisory firm's MDM. If the device held any B3/B4 data locally (this should not happen — see hardening guide §6), escalate to a full incident response.

**Q73. Is there a forensic preservation capability?**  
The audit log + S3 object versioning provide a forensic trail for engagement activities. For cloud deployments, ECS task logs and VPC flow logs are retained in CloudWatch Logs for 90 days. For on-prem, system audit logs (auditd) are retained on the host.

**Q74. Can the platform's LLM be used to assist in incident investigation?**  
No. The LLM must not be given raw incident data. Use M1 (deterministic) mode for any analysis of incident-related spend data. All LLM calls during an active incident investigation require explicit CISO approval.

**Q75. Is there a bug bounty programme for the platform?**  
Not currently. Responsible disclosure: report to security@opex.internal. Acknowledgement within 48 hours, triage within 5 business days, patch SLA per severity (Q69).

---

## Section G — Miscellaneous (Q76–Q82)

**Q76. Is the platform's source code available for review?**  
Yes, under the MSA's source code escrow clause. The client's InfoSec team may perform a code review under supervised conditions. The review is scoped to the deployed version only.

**Q77. What third-party libraries does the platform use?**  
Key runtime dependencies: FastAPI, Pydantic, pandas, python-docx, pptx, PyYAML, Presidio (PII detection), spaCy, redis-py, boto3/azure-identity (optional, provider-dependent). A full SBOM (Software Bill of Materials) in CycloneDX format is available on request.

**Q78. Is there a software composition analysis (SCA) step in the release process?**  
Yes. OWASP Dependency-Check and pip-audit run on every release build. A release is blocked on any known critical vulnerability in a direct dependency. Transitive vulnerabilities are assessed separately.

**Q79. Does the platform use any telemetry that phones home?**  
No. The platform does not send any telemetry, usage metrics, or error reports to the advisory firm's infrastructure. All logs remain within the client's VPC.

**Q80. Is the platform code signed?**  
Release artefacts (Docker image, Helm chart) are signed using Cosign with the advisory firm's signing key. Clients can verify the signature before deployment: `cosign verify opex-api:2.1.0 --key opex-release.pub`.

**Q81. What is the platform's software versioning policy?**  
Semantic versioning (MAJOR.MINOR.PATCH). MAJOR bumps indicate breaking API changes. Sector pack versions are independent (pack_id + semver). The narrative provenance store locks model version and pack version at engagement start — mid-engagement updates require engagement lead sign-off.

**Q82. How is the platform kept secure between engagements?**  
Tear-down destroys all resources at engagement end. There is no persistent infrastructure between engagements. Each new engagement provisions a clean environment from Terraform/Ansible. Engagement data from prior clients is never accessible in a new deployment.
