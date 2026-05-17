# OpEx Intelligence Platform — Security Hardening Guide

**Version:** 2.1  
**Classification:** INTERNAL — Consultant Use Only  
**Review Cycle:** Before each engagement deployment

---

## 1. Deployment Prerequisites

### 1.1 Infrastructure Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS (CIS Level 2 hardened) |
| Python | 3.11 | 3.11 with system packages only |
| Redis | 7.0 | 7.2 with TLS |
| Reverse Proxy | nginx 1.24 | nginx 1.24 + ModSecurity WAF |
| TLS | 1.2 | 1.3 only |

### 1.2 Network Requirements

- Platform must run inside the **client's private VPC** — no public internet exposure.
- All inter-service traffic (API ↔ Redis, API ↔ object storage) must be **TLS-encrypted**.
- Inbound access only via corporate VPN or bastion host — port 8000 must NOT be open to the internet.
- Egress required only for: (a) LLM API calls (Bedrock / Azure OpenAI / Anthropic), (b) regulatory feed polling (GST/SEBI/RBI — whitelist specific endpoints).

---

## 2. Host Hardening (Linux)

### 2.1 OS Configuration

```bash
# Disable unnecessary services
systemctl disable --now bluetooth cups avahi-daemon

# Set strict umask
echo "umask 027" >> /etc/profile.d/hardening.sh

# Restrict core dumps
echo "* hard core 0" >> /etc/security/limits.conf
echo "fs.suid_dumpable = 0" >> /etc/sysctl.d/99-opex.conf

# Enable audit daemon
apt install -y auditd
systemctl enable --now auditd

# Sysctl hardening
cat >> /etc/sysctl.d/99-opex.conf << 'EOF'
net.ipv4.ip_forward = 0
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.all.rp_filter = 1
kernel.randomize_va_space = 2
kernel.dmesg_restrict = 1
EOF
sysctl -p /etc/sysctl.d/99-opex.conf
```

### 2.2 Application User

```bash
# Non-privileged system user with no shell
useradd -r -s /bin/false -d /opt/opex opex
chmod 750 /opt/opex
```

### 2.3 File Permissions

```
/opt/opex/app/          750  opex:opex
/opt/opex/data/         750  opex:opex
/opt/opex/.env          600  opex:opex   # secrets file — never world-readable
/opt/opex/logs/         750  opex:opex
```

---

## 3. TLS Configuration

### 3.1 Nginx TLS (minimum configuration)

```nginx
ssl_protocols TLSv1.3;
ssl_ciphers 'TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256';
ssl_prefer_server_ciphers off;
ssl_session_timeout 1d;
ssl_session_cache shared:SSL:10m;
ssl_session_tickets off;
add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;
add_header X-Content-Type-Options nosniff;
add_header X-Frame-Options DENY;
add_header Content-Security-Policy "default-src 'self'";
```

### 3.2 Certificate Requirements

- Minimum: 2048-bit RSA or P-256 ECDSA
- Preferred: P-384 ECDSA from client's internal PKI
- Validity: ≤ 398 days; auto-renewal via ACME or internal CA tooling
- Store private keys in client KMS (AWS KMS / Azure Key Vault) — never on disk unencrypted

---

## 4. Secret Management

### 4.1 Environment Variables

All secrets (API keys, Redis password, DB password) are injected via:
- **AWS:** Secrets Manager → ECS task definition `secrets` block
- **Azure:** Key Vault → Container Apps managed identity reference
- **On-prem:** Ansible Vault → `/opt/opex/.env` (mode 600)

**Never** hardcode secrets in source, Dockerfile, or Helm values committed to git.

### 4.2 Rotation Policy

| Secret | Rotation Frequency |
|--------|-------------------|
| Anthropic API Key | Per engagement |
| Redis Password | Per engagement |
| KMS key (data) | Annual auto-rotation |
| TLS private key | Per certificate renewal |

### 4.3 Secrets Audit

Before each engagement kick-off, verify:
```bash
# No secrets in env or config files checked into source control
git secret scan   # or trufflehog / gitleaks
grep -rn "sk-ant\|AKIA\|AIza\|password" app/ --include="*.py" --include="*.yaml"
```

---

## 5. Data Classification Enforcement

### 5.1 Band Controls

| Band | LLM Access | Storage | Transmission |
|------|-----------|---------|--------------|
| B1 (Public) | M1/M2/M3 all OK | Plaintext OK | HTTP acceptable (internal) |
| B2 (Internal) | M2/M3 only | AES-256 at rest | TLS 1.3 required |
| B3 (Confidential) | Tokenised only; no raw text to LLM | AES-256 + KMS envelope | TLS 1.3 + mutual TLS |
| B4 (Restricted/PII) | No LLM access; quarantine | AES-256 + KMS + field-level | TLS 1.3 + mTLS; zero-copy principle |

### 5.2 PII Stripping Verification

Before first LLM call on any dataset, verify `pii-stripper` skill output:
- `band_b4_items` must be empty or quarantined
- `recall_confidence` must be ≥ 0.992
- Log the verification result to the immutable audit trail

---

## 6. Network Security

### 6.1 Security Group / Firewall Rules (minimal)

```
# Inbound to opex-api
Allow TCP/8000 from VPN/bastion CIDR
Deny ALL other inbound

# Redis (internal only)
Allow TCP/6379 from opex-api security group only
Deny ALL other

# Egress
Allow TCP/443 to LLM endpoints (whitelist by IP/CIDR)
Allow TCP/443 to regulatory feed endpoints (whitelist)
Deny ALL other egress
```

### 6.2 WAF Rules (if using ModSecurity / AWS WAF)

Enable OWASP Core Rule Set (CRS) 3.3+. Add custom rules:
- Block requests with `../` path traversal in file upload field names
- Block SQL keywords in query parameters
- Rate-limit `/api/upload/` to 10 req/min per IP

---

## 7. Audit Log Requirements

### 7.1 What Must Be Logged (immutable)

Every event below must appear in the append-only audit log before the operation completes:
- User authentication (success and failure)
- File upload (filename, size, session, band classification result)
- LLM call (skill name, model mode, token count — NOT raw prompt)
- Initiative accept/reject (user, initiative_id, timestamp)
- Pack version lock (pack_id, version, engagement_id)
- Tear-down step completion (step_id, executor, timestamp)

### 7.2 Log Integrity

- Logs written to append-only file; no delete/update permitted at OS level (`chattr +a`)
- Ship to client SIEM (CEF / LEEF / JSON) within 60 seconds of event
- Retain locally for engagement duration + 30 days post tear-down
- Include log hash chain: each entry records SHA-256 of previous entry

---

## 8. Container Hardening (Docker / Kubernetes)

### 8.1 Dockerfile Security

```dockerfile
# Use minimal base image
FROM python:3.11-slim-bookworm

# Run as non-root
RUN groupadd -r opex && useradd -r -g opex opex
USER opex

# No privileged capabilities
# Drop ALL, add only what's needed
```

### 8.2 Kubernetes Pod Security

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true   # mount /tmp and /data as emptyDir
  capabilities:
    drop: [ALL]
```

### 8.3 Image Scanning

Scan container image before every deployment:
```bash
trivy image opex-api:2.1.0 --severity HIGH,CRITICAL --exit-code 1
```
Block deployment on any CRITICAL CVE with a fix available.

---

## 9. Data Residency

- All data (spend lines, outputs, backups) must remain in **client's chosen region**:
  - AWS: `ap-south-1` (Mumbai)
  - Azure: `centralindia` (Pune)
  - On-prem: client data centre within India
- LLM API calls: use Bedrock (ap-south-1) or Azure OpenAI (centralindia) for M2 mode.
- **No data may be sent to Anthropic's US endpoints** unless the client has explicitly approved cross-border transfer and documented it in the engagement DPA.

---

## 10. Engagement Tear-Down Checklist

Run `execute_tear_down(engagement_id, dry_run=False)` and verify attestation:

- [ ] Pack-lock files deleted
- [ ] Memory scope cleared
- [ ] Calibration artefacts exported then deleted
- [ ] Audit logs shipped to client SIEM
- [ ] Local backups deleted
- [ ] IaC destroy run (`terraform destroy` or `ansible-playbook teardown.yml`)
- [ ] Cloud tag verification: zero resources with `opex:engagement_id` tag
- [ ] Consultant laptops DLP sweep completed (self-attestation form)
- [ ] Attestation document generated and countersigned by engagement manager
- [ ] Client CISO notified via engagement close email

---

## 11. Vulnerability Disclosure

If you discover a security vulnerability in this platform during an engagement:

1. Do **not** share details in client Slack / email
2. Notify the OpEx platform security team within 24 hours at: security@opex.internal
3. Document the finding in the engagement's restricted risk register (B3 classification)
4. Do not attempt to exploit or validate the vulnerability beyond initial discovery
