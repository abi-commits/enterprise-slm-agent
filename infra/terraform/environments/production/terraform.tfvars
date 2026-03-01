##########################################################################
# environments/production — Terraform Variable Values
#
# DO NOT store secrets here (passwords, keys, tokens).
# Secrets are injected at runtime via Key Vault or CI/CD secret variables.
#
# Commit this file: non-sensitive infrastructure topology only.
##########################################################################

# ---------------------------------------------------------------------------
# Global
# ---------------------------------------------------------------------------
location    = "uksouth"
environment = "production"
name_prefix = "slm-prod"

# ---------------------------------------------------------------------------
# Networking — RFC 1918 address plan
#
#  10.0.0.0/16   VNet
#  ├── 10.0.1.0/24  aks-nodes-subnet     (254 IPs — system + app node VMs)
#  ├── 10.0.2.0/24  private-endpoints    (254 IPs — ACR, KV, Redis, PG PEs)
#  ├── 10.0.3.0/28  postgres-delegated   (14 IPs — PG Flexible Server VNET inj)
#  └── 10.0.4.0/22  aks-pods-subnet      (1022 IPs — CNI overlay pod CIDRs)
# ---------------------------------------------------------------------------
vnet_address_space             = ["10.0.0.0/16"]
aks_nodes_subnet_cidr          = "10.0.1.0/24"
private_endpoints_subnet_cidr  = "10.0.2.0/24"
postgres_delegated_subnet_cidr = "10.0.3.0/28"
aks_pods_subnet_cidr           = "10.0.4.0/22"

# ---------------------------------------------------------------------------
# AKS
# ---------------------------------------------------------------------------

# Kubernetes version — keep within the N-1 minor version of latest GA
kubernetes_version = "1.31"

# System node pool — runs kube-system workloads only (CriticalAddonsOnly taint)
# D4s_v3: 4 vCPU / 16 GiB — sized for system daemons + kube infrastructure
system_pool_vm_size    = "Standard_D4s_v3"
system_pool_node_count = 3    # Fixed count; spread across 3 AZs

# Application node pool — runs API, knowledge, inference services
# D8s_v4: 8 vCPU / 32 GiB — accommodates embedding models in memory
app_pool_vm_size   = "Standard_D8s_v4"
app_pool_min_count = 2    # Minimum for baseline HA (2 AZs minimum)
app_pool_max_count = 5    # Cap autoscale to control egress + cost

# GPU node pool — runs vLLM inference (starts at 0, scales on demand)
# NC6s_v3: 6 vCPU / 112 GiB / 1x V100-16GB — smallest V100 SKU on Azure
# Start at 0 nodes; cluster autoscaler brings up nodes when GPU pods are pending.
gpu_pool_vm_size   = "Standard_NC6s_v3"
gpu_pool_min_count = 0    # Scale-to-zero when not in use
gpu_pool_max_count = 1    # Limit spend during initial rollout — raise as needed

# ---------------------------------------------------------------------------
# PostgreSQL Flexible Server
# ---------------------------------------------------------------------------

# GP_Standard_D4s_v3: 4 vCPU / 16 GiB — General Purpose tier, ZoneRedundant HA
# This sku supports ZoneRedundant high availability required for production.
postgres_sku_name = "GP_Standard_D4s_v3"

# 131072 MiB = 128 GiB initial; enable storage autogrowth via Azure Portal if needed
postgres_storage_mb = 131072

# Postgres 16 is the current stable release supported by Azure PaaS
postgres_version = "16"

# 14-day PITR retention window — satisfies most RPO requirements
postgres_backup_retention_days = 14

# ---------------------------------------------------------------------------
# Azure Cache for Redis
# ---------------------------------------------------------------------------

# Standard C2: 6 GiB RAM, with replication — suitable for session + queue data
# Upgrade to Premium P1 if persistence (RDB/AOF) or geo-replication is required.
redis_sku_name = "Standard"
redis_family   = "C"
redis_capacity = 2    # Standard C2 = 6 GiB replica pair

# ---------------------------------------------------------------------------
# Key Vault — Kubernetes RBAC / Workload Identity
# ---------------------------------------------------------------------------

# Namespace where all application pods run — must match Helm release namespace
kubernetes_namespace = "slm-prod"

# Set of service account names that receive Key Vault Secrets User RBAC +
# federated identity credentials. Add new services here before deploying them.
service_names = [
  "api-service",
  "knowledge-service",
  "inference-service",
  "alembic-job",
  "qdrant-backup",
]
