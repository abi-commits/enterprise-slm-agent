##########################################################################
# Module: acr
#
# Provisions an Azure Container Registry with:
#   - Premium SKU (required for private link + content trust)
#   - Content trust (image signing) and quarantine policy enabled
#   - Public access denied; AKS node subnet is the only allowed network source
#   - Private endpoint inside the shared private-endpoints subnet
#   - Untagged manifest retention to control storage costs
#
# NOTE: AcrPull role assignment for the AKS kubelet identity is created in
# the aks module (avoids circular dependency: acr → aks, aks → acr).
##########################################################################

resource "random_string" "suffix" {
  length  = 4
  upper   = false
  special = false
  numeric = true
}

resource "azurerm_container_registry" "this" {
  name                = "${replace(var.name_prefix, "-", "")}acr${random_string.suffix.result}"
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = var.sku
  admin_enabled       = false # All access via managed identity; no admin credentials.
  tags                = var.tags

  # Quarantine: images are held for Microsoft Defender scanning before AKS
  # can pull them. Requires Premium SKU.
  quarantine_policy_enabled = true

  # Content trust: only signed images may be deployed.
  trust_policy {
    enabled = true
  }

  # Purge untagged manifests after 30 days to prevent storage bloat.
  retention_policy {
    enabled = true
    days    = 30
  }

  # Deny all public network access; only the AKS node subnet and the
  # private endpoint are permitted.
  network_rule_set {
    default_action = "Deny"
    ip_rule        = []
    virtual_network {
      action    = "Allow"
      subnet_id = var.aks_nodes_subnet_id
    }
  }
}

# ---------------------------------------------------------------------------
# Private Endpoint — image pulls never leave the VNet
# ---------------------------------------------------------------------------
resource "azurerm_private_endpoint" "acr" {
  name                = "pe-acr-${var.name_prefix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.private_endpoints_subnet_id
  tags                = var.tags

  private_service_connection {
    name                           = "psc-acr-${var.name_prefix}"
    private_connection_resource_id = azurerm_container_registry.this.id
    subresource_names              = ["registry"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "acr-dns-zone-group"
    private_dns_zone_ids = [var.private_dns_zone_id]
  }
}
