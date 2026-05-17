# OpEx Intelligence Platform — Deployment Checklist

**Last Updated:** May 2026 | **Version:** 3.0

Use this checklist when deploying to AWS, Azure, or on-prem. Refer to § 13 (Deployment Architectures) in the main architecture document for detailed configuration.

---

## Pre-Deployment

### Security & Compliance Review

- [ ] **Data Residency Confirmed**
  - AWS: ap-south-1 (Mumbai)
  - Azure: centralindia (Pune)
  - On-Prem: Client data centre (no egress)

- [ ] **LLM Mode Selected**
  - [ ] M1: Deterministic (no LLM) — Default for BFSI/Healthcare
  - [ ] M2: Cloud India region (Bedrock/Azure OpenAI) — Most engagements
  - [ ] M3: On-prem Ollama — Highly regulated

- [ ] **Data Classification Rules Reviewed**
  - [ ] B1–B4 bands understood (see § 6)
  - [ ] PII detection scope confirmed (≥99.2% recall target)
  - [ ] Quarantine procedure for B4 data established

- [ ] **Audit Log Strategy Confirmed**
  - [ ] SIEM integration endpoint identified
  - [ ] CEF/LEEF format compatibility verified
  - [ ] Retention policy (client owns long-term; platform: 30 days)

- [ ] **Encryption Keys Provisioned**
  - [ ] KMS (AWS) or Key Vault (Azure) configured
  - [ ] Rotation policy set (≥ quarterly)
  - [ ] Backup keys stored securely

- [ ] **Network Access Controlled**
  - [ ] VPN/bastion requirement documented
  - [ ] No public internet access to API
  - [ ] Ingress rule: VPN/bastion IP only

---

## AWS Deployment (ap-south-1)

### Infrastructure Setup

- [ ] **VPC & Networking**
  - [ ] Private VPC created (no public subnets for app)
  - [ ] Bastion host or VPN endpoint configured
  - [ ] Security groups restrict inbound (VPN only)

- [ ] **Compute (ECS Fargate)**
  - [ ] ECS cluster created
  - [ ] Task definition: opex-api (2 vCPU, 4 GB RAM)
  - [ ] runAsNonRoot enabled
  - [ ] CloudWatch Container Insights enabled

- [ ] **Load Balancer**
  - [ ] Application Load Balancer (ALB) created
  - [ ] TLS listener configured (port 443)
  - [ ] Health check path: `/health`

- [ ] **Caching (ElastiCache Redis)**
  - [ ] Redis cluster (cache.t3.micro minimum)
  - [ ] TLS enabled (port 6379 + TLS 1.3)
  - [ ] AUTH token generated and rotated
  - [ ] VPC security group allows ECS → Redis

- [ ] **Storage (S3)**
  - [ ] Bucket created (private, no public access)
  - [ ] Versioning enabled
  - [ ] KMS-SSE encryption enabled
  - [ ] Lifecycle policy: delete after 14 days
  - [ ] Bucket policy: VPC endpoint only

- [ ] **Secrets Management**
  - [ ] Secrets Manager configured
  - [ ] API keys, Redis password stored
  - [ ] Rotation policy set (30 days)
  - [ ] IAM policy: ECS task can read secrets

- [ ] **Logging & Monitoring**
  - [ ] CloudWatch Log Group created
  - [ ] Retention: 90 days
  - [ ] Log encryption: KMS enabled
  - [ ] CloudWatch Alarms set (CPU > 80%, disk > 85%)

- [ ] **Key Management (KMS)**
  - [ ] Customer-Managed Key created
  - [ ] Deletion window: 30 days
  - [ ] Rotation enabled
  - [ ] Key policy allows ECS task

### Deployment Commands

```bash
# Deploy via Terraform (recommended)
cd deploy/terraform/aws
terraform init
terraform plan -var="region=ap-south-1" -var="environment=production"
terraform apply

# Or deploy manually
aws ecs create-cluster --cluster-name opex-prod --region ap-south-1
aws ecs register-task-definition --cli-input-json file://task-def.json
aws ecs create-service --cluster opex-prod --service-name opex-api --task-definition opex-api:1
```

---

## Azure Deployment (centralindia)

### Infrastructure Setup

- [ ] **Resource Group & Networking**
  - [ ] Resource group created (centralindia)
  - [ ] Virtual network configured (private subnets)
  - [ ] VPN or bastion configured

- [ ] **Compute (Container Apps)**
  - [ ] Container Apps environment created
  - [ ] Ingress: disabled (or restricted to internal traffic)
  - [ ] CPU/Memory: 2 vCPU, 4 GB RAM
  - [ ] Container image pulled from registry

- [ ] **Caching (Azure Cache for Redis)**
  - [ ] Redis instance (Standard tier minimum)
  - [ ] TLS: enabled (minimum TLS 1.2)
  - [ ] Non-SSL port: disabled
  - [ ] VNet integration: enabled
  - [ ] AUTH: strong password generated

- [ ] **Storage (Azure Storage Account)**
  - [ ] Storage account (Standard tier, ZRS replication)
  - [ ] CMK encryption (customer-managed key)
  - [ ] Versioning enabled
  - [ ] Soft delete: 14 days
  - [ ] Public access: disabled

- [ ] **Key Management (Key Vault)**
  - [ ] Key Vault (Premium tier)
  - [ ] purge_protection: enabled
  - [ ] Soft delete: 90 days
  - [ ] RSA key: P-4096
  - [ ] Rotation policy: quarterly

- [ ] **Logging & Monitoring**
  - [ ] Application Insights configured
  - [ ] Diagnostics settings: send to Log Analytics
  - [ ] Retention: 90 days
  - [ ] Alerts configured (exceptions, latency)

### Deployment Commands

```bash
# Deploy via Terraform
cd deploy/terraform/azure
terraform init
terraform plan -var="location=centralindia" -var="environment=production"
terraform apply

# Or deploy via Azure CLI
az containerapp create \
  --name opex-api \
  --resource-group opex-rg \
  --image opex-api:latest \
  --ingress internal \
  --target-port 8000 \
  --location centralindia
```

---

## On-Premise Deployment (Ansible)

### Infrastructure Setup

- [ ] **OS & Base Configuration**
  - [ ] Ubuntu 22.04 LTS installed
  - [ ] SSH key-based auth configured (no passwords)
  - [ ] Hostname set (e.g., opex-api.internal)
  - [ ] DNS resolver configured

- [ ] **Hardening**
  - [ ] Firewall (UFW): enable, restrict to SSH + HTTPS
  - [ ] SSH: disable root login, change port (optional)
  - [ ] Core dumps: disabled (`kernel.core_uses_pid=0`)
  - [ ] Auditd: enabled, rules for /app, /var/log
  - [ ] Fail2ban: enabled for SSH, HTTP

- [ ] **Web Server (Nginx)**
  - [ ] Nginx installed & configured
  - [ ] TLS certificate (self-signed or company CA)
  - [ ] TLS 1.3 enabled (ciphers restricted)
  - [ ] ModSecurity WAF rules loaded
  - [ ] CSP header: set (no external resources)
  - [ ] HSTS header: set (max-age=31536000)
  - [ ] SSL labs score: A+ target

- [ ] **Application (systemd)**
  - [ ] opex-api service created (`/etc/systemd/system/opex-api.service`)
  - [ ] User: appuser (no sudo, no shell)
  - [ ] NoNewPrivileges: enabled
  - [ ] ProtectSystem: strict
  - [ ] CapabilityBoundingSet: minimal
  - [ ] systemctl enable opex-api (auto-start)

- [ ] **Caching (Redis)**
  - [ ] Redis installed (bind to 127.0.0.1 only)
  - [ ] requirepass: strong password set
  - [ ] maxmemory: 2GB (adjust based on data)
  - [ ] maxmemory-policy: allkeys-lru
  - [ ] systemctl enable redis (auto-start)

- [ ] **Storage**
  - [ ] Data partition: LVM with encryption (dm-crypt)
  - [ ] Mount options: nodev, nosuid, noexec
  - [ ] Backup destination: cold storage (daily, encrypted)
  - [ ] Backup retention: 30 days

- [ ] **Secrets Management**
  - [ ] Environment file: `/etc/opex-api/env` (mode 0600, owned by appuser)
  - [ ] Secrets rotation: quarterly (manual or cron)
  - [ ] No secrets in code or config files

### Deployment Commands

```bash
# Deploy via Ansible
cd deploy/ansible
ansible-playbook site.yml -i inventory/production.ini --tags "opex-api"

# Manual deployment
git clone https://github.com/[repo]/opex-api.git /app/opex-api
cd /app/opex-api
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
systemctl start opex-api
systemctl status opex-api
```

---

## Kubernetes (Helm) Deployment

### Cluster Preparation

- [ ] **Cluster Setup**
  - [ ] Kubernetes cluster created (1.26+)
  - [ ] Ingress controller installed (nginx, disabled by default)
  - [ ] CNI plugin configured (Calico/Flannel)
  - [ ] DNS working (CoreDNS)

- [ ] **RBAC & Security**
  - [ ] Service account created (opex-api)
  - [ ] RBAC: read ConfigMaps, NO access to secrets (use CSI driver)
  - [ ] Network policies: ingress from ingress controller only
  - [ ] Pod security standards: restricted

- [ ] **Storage**
  - [ ] PersistentVolume (PV) for logs, memory store, audit log
  - [ ] StorageClass configured (SSD preferred)
  - [ ] Backups: daily snapshots to cold storage

- [ ] **Monitoring**
  - [ ] Prometheus operator installed
  - [ ] ServiceMonitor created for opex-api
  - [ ] Grafana dashboards configured
  - [ ] AlertManager rules for critical metrics

### Deployment Commands

```bash
# Add Helm repo
helm repo add opex-intelligence https://charts.opex-intelligence.io
helm repo update

# Deploy Helm chart
helm install opex-api opex-intelligence/opex-api \
  --namespace opex-api \
  --create-namespace \
  --values values-production.yaml

# Verify deployment
kubectl get deployment -n opex-api
kubectl logs -n opex-api -l app=opex-api --tail=50
kubectl port-forward -n opex-api svc/opex-api 8000:80
```

---

## Post-Deployment Validation

### Health Checks

- [ ] **API Reachability**
  ```bash
  curl -k https://opex-api.internal/health
  # Expected: 200 OK, {"status": "healthy"}
  ```

- [ ] **Database Connectivity**
  ```bash
  curl -k https://opex-api.internal/health/ready
  # Expected: 200 OK (ready to accept requests)
  ```

- [ ] **LLM Provider**
  ```bash
  # Test M2 mode (if configured)
  curl -X POST https://opex-api.internal/api/v1/chat \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"message": "test", "session_id": "test-session"}'
  ```

- [ ] **Security Checks**
  - [ ] TLS certificate valid (not self-signed in production)
  - [ ] TLS version 1.3 (check via: `openssl s_client -connect opex-api.internal:443 -tls1_3`)
  - [ ] Security headers present (CSP, HSTS, X-Frame-Options)
  - [ ] PII test: Upload file with test PII, verify B4 quarantine

- [ ] **Audit Logging**
  - [ ] Audit log file created (`/var/log/opex-api/audit.log` or S3/Blob equivalent)
  - [ ] SIEM receiving events (check SIEM dashboard)
  - [ ] Hash chain integrity (run verification script)

- [ ] **Performance**
  - [ ] API latency: < 200 ms for GET requests
  - [ ] Filter latency (cost-room): < 500 ms for 100k lines
  - [ ] Ingestion: < 30 s for 1M-line file

### Configuration Review

- [ ] **Environment Variables Set**
  - [ ] `PYTHONPATH=.`
  - [ ] `LLM_MODE` (M1, M2, or M3)
  - [ ] `DATA_RESIDENCY` (ap-south-1, centralindia, onprem)
  - [ ] `REDIS_URL` or `REDIS_HOST:PORT`
  - [ ] `KMS_KEY_ID` (for S3/Blob encryption)

- [ ] **Configuration Files**
  - [ ] `app/config.py` reviewed
  - [ ] Log level set to INFO (production)
  - [ ] Secrets not logged (no sensitive data in logs)

---

## Go-Live Checklist

- [ ] **Stakeholder Sign-Off**
  - [ ] Security team approved
  - [ ] Compliance team approved
  - [ ] Operations team trained on runbooks

- [ ] **Backup & Disaster Recovery**
  - [ ] Backup strategy tested (restore verification)
  - [ ] RTO/RPO documented (e.g., RTO 30 min, RPO 24 hours)
  - [ ] Runbook for incident response created

- [ ] **Documentation**
  - [ ] Deployment runbook finalized
  - [ ] Known issues documented
  - [ ] Support escalation path established

- [ ] **First Engagement Ready**
  - [ ] Test engagement uploaded
  - [ ] OPAR loop executed successfully
  - [ ] Outputs reviewed (board deck, cost room, business case)

---

## Post-Deployment Operations

### Weekly

- [ ] Monitor logs for errors
- [ ] Verify audit log is flowing to SIEM
- [ ] Check disk usage (< 85% target)

### Monthly

- [ ] Verify backups (restore test)
- [ ] Review security group rules (no drift)
- [ ] Patch OS/dependencies (if not auto-patched)

### Quarterly

- [ ] Security assessment (SIEM events, audit log review)
- [ ] Rotate secrets (API keys, Redis password, TLS cert)
- [ ] Capacity planning (CPU, memory, storage trends)

### Annually

- [ ] Full disaster recovery drill
- [ ] Architecture review (any changes needed?)
- [ ] Engagement data cleanup (tear-down attestations verified)

---

## Troubleshooting Common Issues

| Issue | Diagnosis | Resolution |
|-------|-----------|-----------|
| **API returns 503** | Check OPAR engine, Redis connectivity | Restart app, verify Redis/network |
| **PII detection failing** | Check Presidio model loaded | Verify model download completed |
| **Slow filter queries** | Redis miss or network latency | Check Redis performance, flush stale cache |
| **Audit log not flowing to SIEM** | Network or format issue | Test CEF/LEEF format, verify firewall rules |
| **Tear-down failed** | Permission issue or orphaned resources | Run tear-down in dry-run mode, investigate |

---

**For detailed deployment architecture, see § 13 in main architecture documentation.**
