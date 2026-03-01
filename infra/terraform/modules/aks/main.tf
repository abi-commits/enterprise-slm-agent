##########################################################################
# Module: aks
#
# Provisions the AKS cluster and its three node pools:
#   - systempool  — cluster system add-ons; taint: CriticalAddonsOnly=true:NoSchedule
#   - apppool     — application workloads; autoscaling enabled
#   - gpupool     — vLLM inference; taint: nvidia.com/gpu=present:NoSchedule;
#                   starts at 0 nodes (scale-to-zero) for cost control
#
# Also grants AcrPull on the supplied ACR to the cluster's kubelet identity.
##########################################################################

# ---------------------------------------------------------------------------
# AKS Cluster
# ---------------------------------------------------------------------------
resource "azurerm_kubernetes_cluster" "this" {
  name                = "aks-${var.name_prefix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  dns_prefix          = var.name_prefix
  kubernetes_version  = var.kubernetes_version
  tags                = var.tags

  # OIDC issuer + Workload Identity are required for the Azure Key Vault
  # CSI driver to bind Kubernetes ServiceAccounts to Azure Managed Identities
  # without mounting credentials as secrets.
  oidc_issuer_enabled       = true
  workload_identity_enabled = true

  # System-assigned managed identity drives control-plane operations
  # (node provisioning, subnet attachment, DNS updates).
  identity {
    type = "SystemAssigned"
  }

  # -------------------------------------------------------------------------
  # systempool — cluster system add-ons ONLY
  # Taint excludes all application pods unless they explicitly tolerate it.
  # Zone-redundant across AZs 1/2/3.
  # -------------------------------------------------------------------------
  default_node_pool {
    name           = "systempool"
    vm_size        = var.system_pool.vm_size
    node_count     = var.system_pool.node_count
    vnet_subnet_id = var.aks_nodes_subnet_id
    pod_subnet_id  = var.aks_pods_subnet_id
    os_disk_size_gb = 128
    os_disk_type    = "Ephemeral"
    type            = "VirtualMachineScaleSets"
    zones           = ["1", "2", "3"]

    node_labels = {
      "role"      = "system"
      "agentpool" = "systempool"
    }

    node_taints = ["CriticalAddonsOnly=true:NoSchedule"]

    upgrade_settings {
      max_surge = "33%"
    }
  }

  # -------------------------------------------------------------------------
  # Networking — Azure CNI overlay
  # Nodes get IPs from aks_nodes_subnet; pods from aks_pods_subnet.
  # NetworkPolicy = "azure" enables Kubernetes NetworkPolicy enforcement.
  # -------------------------------------------------------------------------
  network_profile {
    network_plugin      = "azure"
    network_plugin_mode = "overlay"
    network_policy      = "azure"
    load_balancer_sku   = "standard"
    outbound_type       = "loadBalancer"
    service_cidr        = "10.1.0.0/16"
    dns_service_ip      = "10.1.0.10"
  }

  # Azure Policy add-on enforces Pod Security Standards (restricted profile)
  # at admission time without requiring a separate admission webhook.
  azure_policy_enabled = true

  # Secrets Store CSI driver with rotation enabled:
  # secrets pulled from Azure Key Vault and re-synced every 2 minutes.
  key_vault_secrets_provider {
    secret_rotation_enabled  = true
    secret_rotation_interval = "2m"
  }

  # Prevent the autoscaler from resetting node_count on every plan.
  lifecycle {
    ignore_changes = [default_node_pool[0].node_count]
  }
}

# ---------------------------------------------------------------------------
# apppool — application workloads
# Autoscaling; spread across all three availability zones.
# ---------------------------------------------------------------------------
resource "azurerm_kubernetes_cluster_node_pool" "apppool" {
  name                  = "apppool"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.this.id
  vm_size               = var.app_pool.vm_size
  vnet_subnet_id        = var.aks_nodes_subnet_id
  pod_subnet_id         = var.aks_pods_subnet_id
  os_disk_size_gb       = 128
  os_disk_type          = "Ephemeral"
  zones                 = ["1", "2", "3"]

  enable_auto_scaling = true
  min_count           = var.app_pool.min_count
  max_count           = var.app_pool.max_count

  node_labels = {
    "role"      = "app"
    "agentpool" = "apppool"
  }

  upgrade_settings {
    max_surge = "33%"
  }

  tags = var.tags
}

# ---------------------------------------------------------------------------
# gpupool — vLLM GPU inference (scale-to-zero)
# Starts at min=0; AKS Cluster Autoscaler scales up when vLLM pods are
# pending. Taint prevents non-vLLM pods from landing here accidentally.
# ---------------------------------------------------------------------------
resource "azurerm_kubernetes_cluster_node_pool" "gpupool" {
  name                  = "gpupool"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.this.id
  vm_size               = var.gpu_pool.vm_size
  vnet_subnet_id        = var.aks_nodes_subnet_id
  pod_subnet_id         = var.aks_pods_subnet_id
  # NC v3 SKUs require larger OS disk; Ephemeral not available on this family.
  os_disk_size_gb = 256
  os_disk_type    = "Managed"
  # NC SKUs are typically available in a single AZ — pinned to zone 1.
  zones = ["1"]

  enable_auto_scaling = true
  min_count           = 0
  max_count           = var.gpu_pool.max_count

  node_labels = {
    "role"        = "gpu"
    "agentpool"   = "gpupool"
    "accelerator" = "nvidia"
  }

  # Only vLLM pods with the matching toleration will be scheduled here.
  node_taints = ["nvidia.com/gpu=present:NoSchedule"]

  upgrade_settings {
    max_surge = "1"
  }

  tags = var.tags
}

# ---------------------------------------------------------------------------
# RBAC — grant kubelet identity AcrPull on the container registry
# ---------------------------------------------------------------------------
resource "azurerm_role_assignment" "acr_pull" {
  scope                = var.acr_id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_kubernetes_cluster.this.kubelet_identity[0].object_id

  # Explicit dependency: cluster must exist before the role assignment.
  depends_on = [azurerm_kubernetes_cluster.this]
}

# Allow control-plane identity to attach NICs into the node and pod subnets.
resource "azurerm_role_assignment" "network_contributor_nodes" {
  scope                = var.aks_nodes_subnet_id
  role_definition_name = "Network Contributor"
  principal_id         = azurerm_kubernetes_cluster.this.identity[0].principal_id
}

resource "azurerm_role_assignment" "network_contributor_pods" {
  scope                = var.aks_pods_subnet_id
  role_definition_name = "Network Contributor"
  principal_id         = azurerm_kubernetes_cluster.this.identity[0].principal_id
}
