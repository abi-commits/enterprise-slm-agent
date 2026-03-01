# Disaster Recovery Runbook — Enterprise SLM Agent

**Version:** 1.0  
**Last Updated:** 2026-02-26  
**Owner:** Platform Engineering  
**Scope:** Production AKS cluster, `slm-prod` namespace

---

## Table of Contents

1. [RTO / RPO Targets](#rto--rpo-targets)
2. [Backup Schedule](#backup-schedule)
3. [Incident Classification](#incident-classification)
4. [Procedure A — Qdrant Vector Store Recovery](#procedure-a--qdrant-vector-store-recovery)
5. [Procedure B — PostgreSQL Database Recovery](#procedure-b--postgresql-database-recovery)
6. [Procedure C — Full Cluster Failure / AKS Re-provisioning](#procedure-c--full-cluster-failure--aks-re-provisioning)
7. [Procedure D — vLLM Model Weight Recovery](#procedure-d--vllm-model-weight-recovery)
8. [Procedure E — Redis Cache Recovery (Streams)](#procedure-e--redis-cache-recovery-streams)
9. [Validation Checklist](#validation-checklist)
10. [Contacts & Escalation](#contacts--escalation)

---

## RTO / RPO Targets

| Component | RPO | RTO | Backup Method |
|-----------|-----|-----|---------------|
| Qdrant (vectors) | 24 h | 2 h | Daily CronJob snapshot → Azure Blob |
| PostgreSQL (auth/config) | 1 h | 1 h | Continuous → Azure PITR + geo-redundant |
| Redis Streams | Eventual (best-effort) | 15 min | In-memory only; streams are re-populated from Qdrant jobs |
| vLLM model weights | 0 (re-pull from HF Hub) | 30 min | PVC deleted → model re-downloaded on pod start |
| Kubernetes manifests / config | 0 (Git is source of truth) | 30 min | Helm chart in Git |

---

## Backup Schedule

| Resource | CronJob | Destination | Retention |
|----------|---------|-------------|-----------|
| Qdrant snapshots | `0 2 * * *` (02:00 UTC) | Azure Blob `slmprodbackupsa/qdrant-snapshots` | 7 days |
| PostgreSQL | Continuous geo-redundant (platform-managed) | Azure Flexible Server PITR | 35 days |

Verify latest backup exists:

```bash
# Qdrant — list blobs (most recent first)
az storage blob list \
  --account-name slmprodbackupsa \
  --container-name qdrant-snapshots \
  --query "sort_by([], &properties.lastModified)[-5:].[name,properties.lastModified]" \
  -o table

# Trigger an ad-hoc backup immediately
kubectl create job --from=cronjob/qdrant-backup manual-backup-$(date +%s) -n slm-prod
kubectl logs -f -l job-name=manual-backup-* -n slm-prod
```

---

## Incident Classification

| Severity | Definition | Response |
|----------|------------|----------|
| SEV-1 | Complete service outage — no queries served | Page on-call, execute DR within 30 min |
| SEV-2 | Partial outage — degraded search / LLM unavailable | Investigate within 1 h |
| SEV-3 | Single component failure (e.g. Qdrant pod crash-looping) | Self-heal within 4 h |

---

## Procedure A — Qdrant Vector Store Recovery

### Scenario
Qdrant StatefulSet PVC is corrupted, deleted, or the snapshot storage has drifted from source docs.

### Step 1 — Identify latest snapshot

```bash
SNAPSHOT=$(az storage blob list \
  --account-name slmprodbackupsa \
  --container-name qdrant-snapshots \
  --query "sort_by([], &properties.lastModified)[-1:][0].name" \
  -o tsv)
echo "Restoring from snapshot: ${SNAPSHOT}"
```

### Step 2 — Scale down consumers

```bash
# Prevent writes during restore
kubectl scale deployment knowledge-deployment --replicas=0 -n slm-prod
```

### Step 3 — Download snapshot locally (or to a restore pod)

```bash
# Option A: Download to local machine via Azure CLI
az storage blob download \
  --account-name slmprodbackupsa \
  --container-name qdrant-snapshots \
  --name "${SNAPSHOT}" \
  --file /tmp/qdrant-restore.snapshot

# Option B: Download directly into the Qdrant pod using an ephemeral container
kubectl debug -it qdrant-0 -n slm-prod \
  --image=mcr.microsoft.com/azure-cli:2.67.0 \
  -- bash -c "
    az storage blob download \
      --account-name slmprodbackupsa \
      --container-name qdrant-snapshots \
      --name ${SNAPSHOT} \
      --file /tmp/restore.snapshot
    curl -sf -X POST http://localhost:6333/collections/documents/snapshots/upload \
      -H 'Content-Type: application/octet-stream' \
      --data-binary @/tmp/restore.snapshot
"
```

### Step 4 — Upload snapshot to running Qdrant and restore

```bash
QDRANT_POD=$(kubectl get pod -n slm-prod -l app.kubernetes.io/component=qdrant \
  -o jsonpath='{.items[0].metadata.name}')

# Upload snapshot file to Qdrant via REST API
kubectl exec -n slm-prod "${QDRANT_POD}" -- \
  curl -sf -X POST \
    "http://localhost:6333/collections/documents/snapshots/upload" \
    -H "Content-Type: application/octet-stream" \
    --data-binary @/tmp/qdrant-restore.snapshot

# OR: recover from uploaded snapshot filename
# List snapshots available on the server
kubectl exec -n slm-prod "${QDRANT_POD}" -- \
  curl -sf http://localhost:6333/collections/documents/snapshots

# Recover (in-place restore from snapshot name)
kubectl exec -n slm-prod "${QDRANT_POD}" -- \
  curl -sf -X PUT \
    "http://localhost:6333/collections/documents/snapshots/recover" \
    -H "Content-Type: application/json" \
    -d "{\"location\": \"file:///qdrant/snapshots/documents/${SNAPSHOT}\"}"
```

### Step 5 — Verify collection

```bash
kubectl exec -n slm-prod "${QDRANT_POD}" -- \
  curl -sf http://localhost:6333/collections/documents \
  | python3 -m json.tool
# Check "points_count" is non-zero and "status" is "green"
```

### Step 6 — Scale consumers back up

```bash
kubectl scale deployment knowledge-deployment --replicas=2 -n slm-prod
kubectl rollout status deployment/knowledge-deployment -n slm-prod
```

### Step 7 — Validate end-to-end search

```bash
kubectl exec -n slm-prod deploy/api-deployment -- \
  curl -sf -X POST http://localhost:8000/api/v1/query/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test recovery query", "top_k": 3}' \
  | python3 -m json.tool
```

---

## Procedure B — PostgreSQL Database Recovery

The PostgreSQL Flexible Server uses Azure-managed continuous backup with geo-redundant storage and PITR (Point-In-Time Restore) for up to 35 days.

### Step 1 — Determine restore point

```bash
# List restore points available
az postgres flexible-server show \
  --name psql-slm-prod \
  --resource-group rg-slm-prod \
  --query "{earliestRestoreDate:backup.earliestRestoreDate, geoRedundant:backup.geoRedundantBackup}"
```

### Step 2 — Restore to new server

```bash
RESTORE_TIME="2026-02-25T01:00:00Z"   # adjust to last known-good state

az postgres flexible-server restore \
  --name psql-slm-prod-restored \
  --resource-group rg-slm-prod \
  --source-server psql-slm-prod \
  --restore-time "${RESTORE_TIME}"
```

### Step 3 — Update connection string secret in Key Vault

```bash
az keyvault secret set \
  --vault-name kv-slm-prod \
  --name DB-URL \
  --value "postgresql+asyncpg://slmadmin:$(az keyvault secret show --vault-name kv-slm-prod --name DB-PASSWORD --query value -o tsv)@psql-slm-prod-restored.postgres.database.azure.com/slm_db"
```

### Step 4 — Bounce API pods to pick up new secret

```bash
kubectl rollout restart deployment/api-deployment -n slm-prod
kubectl rollout status deployment/api-deployment -n slm-prod --timeout=5m
```

### Step 5 — Run Alembic migrations (if schema version mismatch)

```bash
kubectl create job --from=cronjob/alembic-job alembic-dr-$(date +%s) -n slm-prod
kubectl logs -f -l "job-name=alembic-dr*" -n slm-prod
```

---

## Procedure C — Full Cluster Failure / AKS Re-provisioning

### Trigger
AKS cluster deleted or irrecoverably failed.

### Prerequisites
- Terraform state in Azure Blob backend is intact (or backed up)
- Git repository accessible
- Azure credentials available

### Step 1 — Re-apply Terraform

```bash
cd infra/terraform/environments/production
terraform init -reconfigure
terraform plan -out=tfplan
terraform apply tfplan
```

**Expected duration:** 25–40 minutes (AKS + PostgreSQL + Redis + ACR).

### Step 2 — Re-run Helm deployments

```bash
# Get fresh credentials
az aks get-credentials --name slm-aks-prod --resource-group rg-slm-prod

# Deploy observability stack first (so pods have metrics from day 0)
cd helm/observability
./deploy.sh

# Deploy application stack
helm upgrade --install enterprise-slm helm/enterprise-slm \
  --namespace slm-prod \
  --create-namespace \
  --values helm/enterprise-slm/values.yaml \
  --values helm/enterprise-slm/values-production.yaml \
  --atomic --timeout 15m --wait
```

### Step 3 — Restore Qdrant data

Follow **Procedure A** from Step 1.

### Step 4 — Confirm PostgreSQL PITR was preserved

The Azure Flexible Server is recreated by Terraform.  Restore to the pre-failure point using **Procedure B**.

### Step 5 — Re-activate GPU pool (if applicable)

```bash
CLUSTER_NAME=slm-aks-prod RESOURCE_GROUP=rg-slm-prod ./scripts/gpu-activate.sh
```

---

## Procedure D — vLLM Model Weight Recovery

### Scenario
The `vllm-model-cache` PVC is deleted or its data is corrupted.

### Step 1 — Delete the broken PVC (if pod is stuck)

```bash
kubectl delete pvc vllm-model-cache -n slm-prod --ignore-not-found
```

### Step 2 — Scale down vLLM

```bash
helm upgrade enterprise-slm helm/enterprise-slm \
  --namespace slm-prod \
  --reuse-values \
  --set vllm.enabled=false \
  --wait
```

### Step 3 — Re-enable vLLM (new PVC is created; model re-downloads from HF Hub)

```bash
CLUSTER_NAME=slm-aks-prod RESOURCE_GROUP=rg-slm-prod \
  ./scripts/gpu-activate.sh
```

The model download from Hugging Face Hub takes approximately 5–15 minutes depending on model size and network speed.  Progress is visible in pod logs:

```bash
kubectl logs -n slm-prod -l app.kubernetes.io/component=vllm -f
```

---

## Procedure E — Redis Cache Recovery (Streams)

Redis is used only for rate limiting counters and async job queues (Redis Streams).  In-flight queue items may be lost during a Redis failure.

### Step 1 — Bounce the API deployment (clients reconnect automatically)

```bash
kubectl rollout restart deployment/api-deployment -n slm-prod
kubectl rollout restart deployment/knowledge-deployment -n slm-prod
```

### Step 2 — Verify Redis connectivity

```bash
REDIS_POD=$(kubectl get pod -n slm-prod -l app=redis -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
if [[ -z "${REDIS_POD}" ]]; then
  # Azure Cache for Redis — connect via az CLI
  az redis show --name redis-slm-prod --resource-group rg-slm-prod \
    --query "{state:provisioningState,hostName:hostName}"
else
  kubectl exec -n slm-prod "${REDIS_POD}" -- redis-cli ping
fi
```

### Step 3 — Re-queue failed documents

If knowledge ingestion jobs were dropped, re-trigger ingestion for affected documents via the Knowledge Service API.

---

## Validation Checklist

Run after any DR procedure to confirm system health:

```bash
#!/usr/bin/env bash
set -euo pipefail
NAMESPACE=slm-prod

echo "=== Pod Status ==="
kubectl get pods -n "${NAMESPACE}" -o wide

echo "=== Deployment Readiness ==="
for deploy in api-deployment knowledge-deployment inference-deployment; do
  kubectl rollout status deployment/"${deploy}" -n "${NAMESPACE}" --timeout=2m
done

echo "=== Qdrant Collection ==="
kubectl exec -n "${NAMESPACE}" qdrant-0 -- \
  curl -sf http://localhost:6333/collections/documents \
  | python3 -c "import sys,json; d=json.load(sys.stdin)['result']; print(f'  points: {d[\"points_count\"]}  status: {d[\"status\"]}')"

echo "=== API Health ==="
kubectl exec -n "${NAMESPACE}" deploy/api-deployment -- \
  curl -sf http://localhost:8000/health | python3 -m json.tool

echo "=== Alembic Migration Version ==="
kubectl get configmap alembic-version -n "${NAMESPACE}" -o jsonpath='{.data.version}' 2>/dev/null \
  || echo "  (no version configmap — check job logs)"

echo "=== Prometheus Scrape Targets ==="
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
PF_PID=$!
sleep 3
curl -sf http://localhost:9090/api/v1/targets | \
  python3 -c "
import sys,json
t=json.load(sys.stdin)['data']['activeTargets']
for x in t:
    if 'slm-prod' in x.get('labels',{}).get('namespace',''):
        print(f'  {x[\"labels\"][\"job\"]}: {x[\"health\"]}')
"
kill "${PF_PID}" 2>/dev/null || true
```

---

## Contacts & Escalation

| Role | Responsibility | Contact |
|------|---------------|---------|
| Platform On-Call | Cluster, networking, Terraform | PagerDuty: `platform-oncall` |
| ML Engineering | vLLM, model quality | Slack: `#ml-engineering` |
| Data Engineering | Qdrant, knowledge ingestion | Slack: `#data-engineering` |
| Azure Support | AKS, PostgreSQL, Blob Storage | Azure portal → Support + billing |

**Alertmanager webhook:** configured via K8s secret `alert-webhook-url` in `monitoring` namespace.  
**Grafana:** `http://localhost:3000` (port-forward) or internal ingress URL.  
**Runbook repo:** `abi-commits/enterprise-slm-agent` → `docs/runbooks/`
