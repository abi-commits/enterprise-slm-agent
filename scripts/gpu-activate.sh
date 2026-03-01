#!/usr/bin/env bash
# =============================================================================
# gpu-activate.sh — Enterprise SLM GPU Node Pool Activation
#
# Run this ONCE after the Terraform GPU pool module has been applied.
# It validates the full GPU stack and then enables vLLM in the Helm chart.
#
# Steps:
#   1.  Verify AKS GPU node pool is Ready
#   2.  Verify NVIDIA device plugin DaemonSet is healthy
#   3.  Verify nvidia.com/gpu resource is visible on GPU nodes
#   4.  Run a quick GPU smoke test (nvidia-smi in a short-lived pod)
#   5.  Verify NVIDIA RuntimeClass exists
#   6.  Flip vllm.enabled=true via Helm upgrade (no downtime for other services)
#   7.  Wait for vLLM Deployment rollout
#   8.  Smoke-test vLLM /v1/models endpoint
#
# Usage:
#   CLUSTER_NAME=slm-aks-prod RESOURCE_GROUP=rg-slm-prod ./scripts/gpu-activate.sh
#
# Environment variables:
#   CLUSTER_NAME     AKS cluster name (required)
#   RESOURCE_GROUP   Azure resource group (required)
#   GPU_NODE_POOL    Node pool name (default: gpupool)
#   NAMESPACE        App namespace (default: slm-prod)
#   HELM_RELEASE     Helm release name (default: enterprise-slm)
#   HELM_VALUES      Path to production values file
#   DRY_RUN          Set to "true" to skip Helm upgrade (default: false)
# =============================================================================
set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:?CLUSTER_NAME must be set}"
RESOURCE_GROUP="${RESOURCE_GROUP:?RESOURCE_GROUP must be set}"
GPU_NODE_POOL="${GPU_NODE_POOL:-gpupool}"
NAMESPACE="${NAMESPACE:-slm-prod}"
HELM_RELEASE="${HELM_RELEASE:-enterprise-slm}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELM_DIR="${SCRIPT_DIR}/../helm/enterprise-slm"
HELM_VALUES="${HELM_VALUES:-${HELM_DIR}/values-production.yaml}"
DRY_RUN="${DRY_RUN:-false}"

# ── Colour helpers ─────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'
log()  { echo -e "${BLUE}[$(date -u +%H:%M:%S)]${NC} $*"; }
ok()   { echo -e "${GREEN}  ✔${NC} $*"; }
warn() { echo -e "${YELLOW}  ⚠${NC} $*"; }
die()  { echo -e "${RED}  ✘ FATAL:${NC} $*" >&2; exit 1; }
step() { echo -e "\n${BOLD}Step $1:${NC} $2"; }

# ── Step 1: AKS credentials + node pool check ─────────────────────────────
step 1 "Fetching AKS credentials"
az aks get-credentials \
  --name "${CLUSTER_NAME}" \
  --resource-group "${RESOURCE_GROUP}" \
  --overwrite-existing
ok "kubectl context: $(kubectl config current-context)"

step 2 "Verifying GPU node pool '${GPU_NODE_POOL}'"
GPU_NODES=$(kubectl get nodes \
  -l "agentpool=${GPU_NODE_POOL}" \
  --no-headers 2>/dev/null | wc -l | tr -d ' ')

if [[ "${GPU_NODES}" -eq 0 ]]; then
  die "No nodes found with label agentpool=${GPU_NODE_POOL}. Run 'terraform apply' first."
fi
log "Found ${GPU_NODES} GPU node(s)"

NOT_READY=$(kubectl get nodes \
  -l "agentpool=${GPU_NODE_POOL}" \
  --no-headers | grep -v " Ready" | wc -l | tr -d ' ')
if [[ "${NOT_READY}" -gt 0 ]]; then
  die "${NOT_READY} GPU node(s) are not in Ready state. Check 'kubectl describe node'."
fi
ok "All GPU nodes are Ready"

# ── Step 3: NVIDIA device plugin DaemonSet ─────────────────────────────────
step 3 "Checking NVIDIA device plugin DaemonSet"
DESIRED=$(kubectl get daemonset nvidia-device-plugin \
  -n nvidia-device-plugin \
  -o jsonpath='{.status.desiredNumberScheduled}' 2>/dev/null || echo "0")
READY=$(kubectl get daemonset nvidia-device-plugin \
  -n nvidia-device-plugin \
  -o jsonpath='{.status.numberReady}' 2>/dev/null || echo "0")

if [[ "${DESIRED}" -eq 0 ]]; then
  die "NVIDIA device plugin DaemonSet not found. Deploy enterprise-slm chart with nvidia.devicePlugin.enabled=true"
fi
if [[ "${READY}" -ne "${DESIRED}" ]]; then
  die "NVIDIA device plugin: ${READY}/${DESIRED} pods ready. Wait and retry."
fi
ok "NVIDIA device plugin: ${READY}/${DESIRED} pods ready"

# ── Step 4: GPU resource availability ─────────────────────────────────────
step 4 "Verifying nvidia.com/gpu extended resource on nodes"
GPU_NODES_LIST=$(kubectl get nodes \
  -l "agentpool=${GPU_NODE_POOL}" \
  -o jsonpath='{.items[*].metadata.name}')

for node in ${GPU_NODES_LIST}; do
  GPU_COUNT=$(kubectl get node "${node}" \
    -o jsonpath='{.status.allocatable.nvidia\.com/gpu}' 2>/dev/null || echo "0")
  if [[ "${GPU_COUNT:-0}" -eq 0 ]]; then
    die "Node ${node} has no allocatable nvidia.com/gpu. NVIDIA plugin may still be initialising."
  fi
  ok "Node ${node}: ${GPU_COUNT} GPU(s) allocatable"
done

# ── Step 5: GPU smoke test ─────────────────────────────────────────────────
step 5 "Running GPU smoke test (nvidia-smi)"
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: gpu-smoke-test
  namespace: ${NAMESPACE}
  labels:
    app: gpu-smoke-test
spec:
  restartPolicy: Never
  runtimeClassName: nvidia
  nodeSelector:
    agentpool: ${GPU_NODE_POOL}
  tolerations:
    - key: "nvidia.com/gpu"
      operator: "Equal"
      value: "present"
      effect: "NoSchedule"
  containers:
    - name: nvidia-smi
      image: nvidia/cuda:12.1.0-base-ubuntu22.04
      command: ["nvidia-smi"]
      resources:
        limits:
          nvidia.com/gpu: "1"
      securityContext:
        allowPrivilegeEscalation: false
        capabilities:
          drop: [ALL]
EOF

log "Waiting for smoke test pod to complete (max 3m)..."
kubectl wait pod/gpu-smoke-test \
  -n "${NAMESPACE}" \
  --for=condition=Ready \
  --timeout=60s 2>/dev/null || true

kubectl wait pod/gpu-smoke-test \
  -n "${NAMESPACE}" \
  --for=jsonpath='{.status.phase}'=Succeeded \
  --timeout=120s \
  || die "GPU smoke test pod did not succeed. Check: kubectl logs gpu-smoke-test -n ${NAMESPACE}"

echo ""
log "nvidia-smi output:"
kubectl logs gpu-smoke-test -n "${NAMESPACE}"
kubectl delete pod gpu-smoke-test -n "${NAMESPACE}" --ignore-not-found
ok "GPU smoke test passed"

# ── Step 6: RuntimeClass ───────────────────────────────────────────────────
step 6 "Checking NVIDIA RuntimeClass"
if kubectl get runtimeclass nvidia &>/dev/null; then
  ok "RuntimeClass 'nvidia' exists"
else
  die "RuntimeClass 'nvidia' not found. Deploy enterprise-slm chart first (nvidia.devicePlugin.enabled=true)"
fi

# ── Step 7: Enable vLLM via Helm upgrade ──────────────────────────────────
step 7 "Enabling vLLM in Helm release '${HELM_RELEASE}'"
if [[ "${DRY_RUN}" == "true" ]]; then
  warn "DRY_RUN=true — skipping Helm upgrade"
  log "To apply manually:"
  echo "  helm upgrade ${HELM_RELEASE} ${HELM_DIR} \\"
  echo "    --namespace ${NAMESPACE} \\"
  echo "    --values ${HELM_VALUES} \\"
  echo "    --set vllm.enabled=true \\"
  echo "    --set vllm.runtimeClassName=nvidia \\"
  echo "    --atomic --timeout 10m --wait"
else
  helm upgrade "${HELM_RELEASE}" "${HELM_DIR}" \
    --namespace "${NAMESPACE}" \
    --values "${HELM_VALUES}" \
    --set vllm.enabled=true \
    --set vllm.runtimeClassName=nvidia \
    --reuse-values \
    --atomic \
    --timeout 10m \
    --wait
  ok "Helm upgrade complete"
fi

# ── Step 8: vLLM rollout status ────────────────────────────────────────────
step 8 "Waiting for vLLM Deployment rollout"
if [[ "${DRY_RUN}" != "true" ]]; then
  kubectl rollout status deployment/vllm \
    -n "${NAMESPACE}" \
    --timeout=10m \
  || die "vLLM rollout failed. Check: kubectl describe pod -l app.kubernetes.io/component=vllm -n ${NAMESPACE}"
  ok "vLLM Deployment rolled out"
fi

# ── Step 9: vLLM endpoint smoke test ──────────────────────────────────────
step 9 "Smoke-testing vLLM /v1/models"
if [[ "${DRY_RUN}" != "true" ]]; then
  VLLM_POD=$(kubectl get pod \
    -n "${NAMESPACE}" \
    -l "app.kubernetes.io/component=vllm" \
    -o jsonpath='{.items[0].metadata.name}')

  MAX_WAIT=300
  WAITED=0
  while true; do
    HTTP_CODE=$(kubectl exec -n "${NAMESPACE}" "${VLLM_POD}" -- \
      curl -sf -o /dev/null -w "%{http_code}" http://localhost:8000/v1/models 2>/dev/null || echo "000")
    if [[ "${HTTP_CODE}" == "200" ]]; then break; fi
    if [[ ${WAITED} -ge ${MAX_WAIT} ]]; then
      die "vLLM /v1/models did not return 200 after ${MAX_WAIT}s. HTTP=${HTTP_CODE}"
    fi
    log "Waiting for vLLM model server... (HTTP=${HTTP_CODE}, waited=${WAITED}s)"
    sleep 15; (( WAITED += 15 ))
  done
  ok "vLLM /v1/models returned HTTP 200"

  log "Loaded models:"
  kubectl exec -n "${NAMESPACE}" "${VLLM_POD}" -- \
    curl -sf http://localhost:8000/v1/models | python3 -m json.tool || true
fi

# ── Summary ────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  GPU Activation Complete${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${BOLD}Test inference from inside the cluster:${NC}"
echo "    kubectl exec -n ${NAMESPACE} deploy/inference-deployment -- \\"
echo "      curl -s http://vllm.${NAMESPACE}.svc.cluster.local:8000/v1/models"
echo ""
echo -e "  ${BOLD}Tail vLLM logs:${NC}"
echo "    kubectl logs -n ${NAMESPACE} -l app.kubernetes.io/component=vllm -f"
echo ""
echo -e "  ${BOLD}Monitor GPU utilisation:${NC}"
echo "    kubectl exec -n ${NAMESPACE} \$(kubectl get pod -n ${NAMESPACE} -l app.kubernetes.io/component=vllm -o jsonpath='{.items[0].metadata.name}') -- nvidia-smi dmon -s u"
echo ""
