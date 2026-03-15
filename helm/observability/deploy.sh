#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# deploy.sh — Enterprise Athena Observability Stack Deployment
#
# Installs the full observability stack into the 'monitoring' namespace:
#   1. Helm repos
#   2. Namespace + RBAC (PSS baseline)
#   3. K8s secrets (Grafana admin, alert webhook URL)
#   4. kube-prometheus-stack  (Prometheus, Alertmanager, Grafana)
#   5. Loki  (log aggregation)
#   6. Promtail  (log shipper DaemonSet)
#   7. Tempo  (distributed tracing)
#   8. ServiceMonitors, PrometheusRules, Grafana dashboard ConfigMaps
#   9. OTEL env-var patch on enterprise-athena deployments
#
# Prerequisites:
#   - kubectl context pointing at the target AKS cluster
#   - helm >= 3.14, kubectl >= 1.29
#   - Azure Key Vault secrets sync already handled by the enterprise-athena chart
#     (SecretProviderClass + CSI driver); the alert webhook URL must be
#     pre-staged in Key Vault as:  kv-<prefix>-prod/ALERT_WEBHOOK_URL
#
# Usage:
#   chmod +x deploy.sh
#   NAMESPACE=monitoring CLUSTER_NAME=athena-aks-prod ./deploy.sh
#   SKIP_SECRETS=true ./deploy.sh        # skip secret re-creation if exists
# ---------------------------------------------------------------------------
set -euo pipefail

# ── Configurable defaults ──────────────────────────────────────────────────
NAMESPACE="${NAMESPACE:-monitoring}"
APP_NAMESPACE="${APP_NAMESPACE:-athena-prod}"
CLUSTER_NAME="${CLUSTER_NAME:-athena-aks-prod}"
SKIP_SECRETS="${SKIP_SECRETS:-false}"

# Pinned chart versions — update via `helm search repo <repo/chart> --versions`
KUBE_PROMETHEUS_VERSION="${KUBE_PROMETHEUS_VERSION:-67.9.0}"
LOKI_VERSION="${LOKI_VERSION:-6.29.0}"
PROMTAIL_VERSION="${PROMTAIL_VERSION:-6.16.6}"
TEMPO_VERSION="${TEMPO_VERSION:-1.14.0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Colour helpers ─────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${BLUE}▶${NC} $*"; }
ok()   { echo -e "${GREEN}✔${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
die()  { echo -e "${RED}✘ FATAL:${NC} $*" >&2; exit 1; }

# ── Preflight checks ───────────────────────────────────────────────────────
preflight() {
  log "Running preflight checks..."
  command -v helm   >/dev/null 2>&1 || die "helm not found — install helm >= 3.14"
  command -v kubectl >/dev/null 2>&1 || die "kubectl not found"

  local ctx
  ctx=$(kubectl config current-context 2>/dev/null) \
    || die "No kubectl context set — run 'az aks get-credentials --name ${CLUSTER_NAME} ...'"
  warn "Target context: ${BOLD}${ctx}${NC}"
  echo -n "  Continue? [y/N] "
  read -r ans
  [[ "${ans}" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }
  ok "Preflight passed"
}

# ── 1. Helm repos ─────────────────────────────────────────────────────────
add_repos() {
  log "Adding Helm repositories..."
  helm repo add prometheus-community https://prometheus-community.github.io/helm-charts 2>/dev/null || true
  helm repo add grafana https://grafana.github.io/helm-charts 2>/dev/null || true
  helm repo update
  ok "Helm repos ready"
}

# ── 2. Namespace ──────────────────────────────────────────────────────────
create_namespace() {
  log "Applying monitoring namespace (PSS baseline)..."
  kubectl apply -f "${SCRIPT_DIR}/namespace.yaml"
  ok "Namespace '${NAMESPACE}' ready"
}

# ── 3. K8s secrets ────────────────────────────────────────────────────────
create_secrets() {
  if [[ "${SKIP_SECRETS}" == "true" ]]; then
    warn "SKIP_SECRETS=true — skipping secret creation"
    return
  fi

  log "Creating Grafana admin secret..."
  if kubectl get secret grafana-admin -n "${NAMESPACE}" &>/dev/null; then
    warn "Secret 'grafana-admin' already exists — skipping"
  else
    local gf_pass
    gf_pass="$(openssl rand -base64 32 | tr -dc 'A-Za-z0-9!@#$%^&*' | head -c 32)"
    kubectl create secret generic grafana-admin \
      --namespace "${NAMESPACE}" \
      --from-literal=admin-user=admin \
      --from-literal=admin-password="${gf_pass}"
    echo -e "  ${BOLD}Grafana admin password:${NC} ${gf_pass}"
    echo "  (Store this securely — it will not be shown again)"
    ok "Secret 'grafana-admin' created"
  fi

  log "Creating alert-webhook-url secret placeholder..."
  if kubectl get secret alert-webhook-url -n "${NAMESPACE}" &>/dev/null; then
    warn "Secret 'alert-webhook-url' already exists — skipping"
  else
    local webhook_url="${ALERT_WEBHOOK_URL:-https://placeholder.example.com/alerts}"
    if [[ "${webhook_url}" == "https://placeholder.example.com/alerts" ]]; then
      warn "ALERT_WEBHOOK_URL not set — creating placeholder (update before enabling Alertmanager)"
    fi
    kubectl create secret generic alert-webhook-url \
      --namespace "${NAMESPACE}" \
      --from-literal=ALERT_WEBHOOK_URL="${webhook_url}"
    ok "Secret 'alert-webhook-url' created"
  fi
}

# ── 4. kube-prometheus-stack ──────────────────────────────────────────────
install_kube_prometheus() {
  log "Installing kube-prometheus-stack v${KUBE_PROMETHEUS_VERSION}..."
  helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
    --version "${KUBE_PROMETHEUS_VERSION}" \
    --namespace "${NAMESPACE}" \
    --create-namespace \
    --values "${SCRIPT_DIR}/kube-prometheus-stack/values.yaml" \
    --set prometheus.prometheusSpec.externalLabels.cluster="${CLUSTER_NAME}" \
    --atomic \
    --timeout 10m \
    --wait
  ok "kube-prometheus-stack installed"
}

# ── 5. Loki ───────────────────────────────────────────────────────────────
install_loki() {
  log "Installing Loki v${LOKI_VERSION}..."
  helm upgrade --install loki grafana/loki \
    --version "${LOKI_VERSION}" \
    --namespace "${NAMESPACE}" \
    --values "${SCRIPT_DIR}/loki/values.yaml" \
    --atomic \
    --timeout 5m \
    --wait
  ok "Loki installed"
}

# ── 6. Promtail ───────────────────────────────────────────────────────────
install_promtail() {
  log "Installing Promtail v${PROMTAIL_VERSION}..."
  helm upgrade --install promtail grafana/promtail \
    --version "${PROMTAIL_VERSION}" \
    --namespace "${NAMESPACE}" \
    --values "${SCRIPT_DIR}/loki/promtail.yaml" \
    --atomic \
    --timeout 5m \
    --wait
  ok "Promtail installed"
}

# ── 7. Tempo ──────────────────────────────────────────────────────────────
install_tempo() {
  log "Installing Tempo v${TEMPO_VERSION}..."
  helm upgrade --install tempo grafana/tempo \
    --version "${TEMPO_VERSION}" \
    --namespace "${NAMESPACE}" \
    --values "${SCRIPT_DIR}/tempo/values.yaml" \
    --atomic \
    --timeout 5m \
    --wait
  ok "Tempo installed"
}

# ── 8. CRD-based resources (ServiceMonitors, PrometheusRules, Dashboards) ──
apply_crd_resources() {
  log "Applying ServiceMonitors..."
  kubectl apply -f "${SCRIPT_DIR}/servicemonitors/"
  ok "ServiceMonitors applied"

  log "Applying PrometheusRules..."
  kubectl apply -f "${SCRIPT_DIR}/prometheusrules/"
  ok "PrometheusRules applied"

  log "Applying Grafana dashboard ConfigMaps..."
  kubectl apply -f "${SCRIPT_DIR}/dashboards/"
  ok "Grafana dashboards applied"
}

# ── 9. Patch enterprise-athena deployments with OTEL endpoint ────────────────
patch_otel_env() {
  log "Patching enterprise-athena deployments with OTEL_EXPORTER_OTLP_ENDPOINT..."
  local endpoint="http://tempo.${NAMESPACE}.svc.cluster.local:4317"
  local deployments=("api-deployment" "knowledge-deployment" "inference-deployment")

  for deploy in "${deployments[@]}"; do
    if kubectl get deployment "${deploy}" -n "${APP_NAMESPACE}" &>/dev/null; then
      kubectl set env deployment/"${deploy}" \
        -n "${APP_NAMESPACE}" \
        OTEL_EXPORTER_OTLP_ENDPOINT="${endpoint}" \
        OTEL_TRACES_SAMPLER="parentbased_traceidratio" \
        OTEL_TRACES_SAMPLER_ARG="0.1" \
        --overwrite
      ok "Patched deployment/${deploy}"
    else
      warn "Deployment '${deploy}' not found in namespace '${APP_NAMESPACE}' — skip"
    fi
  done
}

# ── 10. Smoke-test ────────────────────────────────────────────────────────
smoke_test() {
  log "Running smoke tests..."

  # Wait for Prometheus to be ready
  kubectl rollout status statefulset/prometheus-kube-prometheus-stack-prometheus \
    -n "${NAMESPACE}" --timeout=3m \
    && ok "Prometheus ready" || warn "Prometheus not ready — check logs"

  # Wait for Grafana
  kubectl rollout status deployment/kube-prometheus-stack-grafana \
    -n "${NAMESPACE}" --timeout=3m \
    && ok "Grafana ready" || warn "Grafana not ready — check logs"

  # Wait for Loki
  kubectl rollout status statefulset/loki \
    -n "${NAMESPACE}" --timeout=3m \
    && ok "Loki ready" || warn "Loki not ready — check logs"

  # Wait for Tempo
  kubectl rollout status statefulset/tempo \
    -n "${NAMESPACE}" --timeout=3m \
    && ok "Tempo ready" || warn "Tempo not ready — check logs"
}

# ── Summary ───────────────────────────────────────────────────────────────
print_summary() {
  echo ""
  echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"
  echo -e "${GREEN}  Observability Stack Deployment Complete${NC}"
  echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"
  echo ""
  echo -e "  ${BOLD}Access Grafana locally:${NC}"
  echo "    kubectl port-forward -n ${NAMESPACE} svc/kube-prometheus-stack-grafana 3000:80"
  echo "    open http://localhost:3000  (admin / <grafana-admin secret>)"
  echo ""
  echo -e "  ${BOLD}Access Prometheus locally:${NC}"
  echo "    kubectl port-forward -n ${NAMESPACE} svc/kube-prometheus-stack-prometheus 9090:9090"
  echo ""
  echo -e "  ${BOLD}Access Tempo OTLP endpoint (from app pods):${NC}"
  echo "    http://tempo.${NAMESPACE}.svc.cluster.local:4317  (gRPC)"
  echo "    http://tempo.${NAMESPACE}.svc.cluster.local:4318  (HTTP)"
  echo ""
  echo -e "  ${BOLD}Check alert webhook URL:${NC}"
  echo "    kubectl get secret alert-webhook-url -n ${NAMESPACE} -o jsonpath='{.data.ALERT_WEBHOOK_URL}' | base64 -d"
  echo ""
  echo -e "  ${BOLD}Retrieve Grafana admin password:${NC}"
  echo "    kubectl get secret grafana-admin -n ${NAMESPACE} -o jsonpath='{.data.admin-password}' | base64 -d"
  echo ""
}

# ── Teardown helper (run with --teardown flag) ─────────────────────────────
teardown() {
  warn "Tearing down observability stack..."
  echo -n "  Are you sure? This deletes ALL monitoring data. [yes/N] "
  read -r ans
  [[ "${ans}" == "yes" ]] || { echo "Aborted."; exit 0; }

  helm uninstall promtail      -n "${NAMESPACE}" 2>/dev/null || true
  helm uninstall tempo         -n "${NAMESPACE}" 2>/dev/null || true
  helm uninstall loki          -n "${NAMESPACE}" 2>/dev/null || true
  helm uninstall kube-prometheus-stack -n "${NAMESPACE}" 2>/dev/null || true

  # Remove CRD-owned resources
  kubectl delete -f "${SCRIPT_DIR}/servicemonitors/"  --ignore-not-found
  kubectl delete -f "${SCRIPT_DIR}/prometheusrules/"  --ignore-not-found
  kubectl delete -f "${SCRIPT_DIR}/dashboards/"       --ignore-not-found

  # Remove PVCs (data is lost — intentional)
  kubectl delete pvc -n "${NAMESPACE}" \
    -l "app.kubernetes.io/name in (prometheus,grafana,loki,tempo)" \
    --ignore-not-found

  # Remove namespace (wait for finalizers)
  kubectl delete namespace "${NAMESPACE}" --ignore-not-found
  ok "Observability stack torn down"
}

# ── Entrypoint ────────────────────────────────────────────────────────────
main() {
  if [[ "${1:-}" == "--teardown" ]]; then
    teardown
    exit 0
  fi

  echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"
  echo -e "${BOLD}  Enterprise Athena — Observability Stack Deployment${NC}"
  echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"
  echo "  Namespace : ${NAMESPACE}"
  echo "  App NS    : ${APP_NAMESPACE}"
  echo "  Cluster   : ${CLUSTER_NAME}"
  echo ""

  preflight
  add_repos
  create_namespace
  create_secrets
  install_kube_prometheus
  install_loki
  install_promtail
  install_tempo
  apply_crd_resources
  patch_otel_env
  smoke_test
  print_summary
}

main "$@"
