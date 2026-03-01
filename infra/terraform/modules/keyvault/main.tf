##########################################################################
# Module: keyvault
#
# Provisions:
#   - Azure Key Vault with RBAC model, purge protection, private endpoint
#   - Per-service User-Assigned Managed Identities
#   - Federated Identity Credentials (AKS Workload Identity binding)
#   - Minimal RBAC: each service identity gets 'Key Vault Secrets User' only
#   - Placeholder secret names seeded on first apply (values = REPLACE_ME)
#
# Secret VALUES are intentionally not managed after first seeding.
# Operators rotate secrets via:
#   az keyvault secret set --vault-name <name> --name <secret> --value <value>
# Terraform uses lifecycle.ignore_changes = [value] to avoid overwriting.
##########################################################################

resource "random_string" "kv_suffix" {
  length  = 4
  upper   = false
  special = false
  numeric = true
}

# ---------------------------------------------------------------------------
# Key Vault
# ---------------------------------------------------------------------------
resource "azurerm_key_vault" "this" {
  name                = "kv-${var.name_prefix}-${random_string.kv_suffix.result}"
  location            = var.location
  resource_group_name = var.resource_group_name
  tenant_id           = var.tenant_id
  sku_name            = "standard"
  tags                = var.tags

  # RBAC model: access controlled via Azure role assignments, not access policies.
  enable_rbac_authorization = true

  # Soft-delete: secrets recoverable for 90 days after deletion.
  # Purge protection: no one (including the operator) can permanently delete
  # until the retention window passes — critical for compliance.
  soft_delete_retention_days = 90
  purge_protection_enabled   = true

  # No public access — all traffic must come via the private endpoint.
  public_network_access_enabled = false

  network_acls {
    bypass         = "AzureServices" # Allow trusted Azure services (Defender, Monitor)
    default_action = "Deny"
    ip_rules       = []
    virtual_network_subnet_ids = [
      var.aks_nodes_subnet_id,
      var.private_endpoints_subnet_id,
    ]
  }
}

# ---------------------------------------------------------------------------
# Private Endpoint — KV only reachable inside the VNet
# ---------------------------------------------------------------------------
resource "azurerm_private_endpoint" "keyvault" {
  name                = "pe-kv-${var.name_prefix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.private_endpoints_subnet_id
  tags                = var.tags

  private_service_connection {
    name                           = "psc-kv-${var.name_prefix}"
    private_connection_resource_id = azurerm_key_vault.this.id
    subresource_names              = ["vault"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "kv-dns-zone-group"
    private_dns_zone_ids = [var.private_dns_zone_id]
  }
}

# ---------------------------------------------------------------------------
# RBAC — Terraform caller needs Key Vault Administrator to seed secrets
# ---------------------------------------------------------------------------
resource "azurerm_role_assignment" "terraform_kv_admin" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Administrator"
  principal_id         = var.terraform_caller_object_id
}

# ---------------------------------------------------------------------------
# Per-service User-Assigned Managed Identities
# ---------------------------------------------------------------------------
resource "azurerm_user_assigned_identity" "services" {
  for_each = var.service_names

  name                = "mi-${var.name_prefix}-${each.value}"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

# ---------------------------------------------------------------------------
# Federated Identity Credentials
# Binds each Kubernetes ServiceAccount (sa-<service>) in the target namespace
# to its corresponding Azure Managed Identity via OIDC token exchange.
# No secrets or certificates are required; the pod's projected service account
# token is exchanged for an Azure AD token at runtime.
# ---------------------------------------------------------------------------
resource "azurerm_federated_identity_credential" "services" {
  for_each = var.service_names

  name                = "fic-${each.value}"
  resource_group_name = var.resource_group_name
  parent_id           = azurerm_user_assigned_identity.services[each.value].id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = var.oidc_issuer_url
  subject             = "system:serviceaccount:${var.kubernetes_namespace}:sa-${each.value}"
}

# ---------------------------------------------------------------------------
# RBAC — Minimal 'Key Vault Secrets User' per service identity
# Each service can only READ secrets; it cannot create, update, or delete.
# ---------------------------------------------------------------------------
resource "azurerm_role_assignment" "service_secrets_user" {
  for_each = var.service_names

  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.services[each.value].principal_id
}

# ---------------------------------------------------------------------------
# Placeholder Secrets
# Seeded with REPLACE_ME values on first apply. Operators set real values
# via az CLI or the portal. lifecycle.ignore_changes prevents Terraform from
# overwriting after rotation.
#
# Required secrets expected by application services:
#   jwt-secret-key          — API service JWT signing key
#   postgres-connection-string — Full asyncpg DSN (set by postgres module output + operator)
#   redis-connection-string    — TLS Redis DSN (set by redis module output + operator)
#   alert-webhook-url          — Slack/Teams incoming webhook
#   huggingface-hub-token      — HuggingFace gated model access
# ---------------------------------------------------------------------------
locals {
  placeholder_secrets = toset([
    "jwt-secret-key",
    "postgres-connection-string",
    "redis-connection-string",
    "alert-webhook-url",
    "huggingface-hub-token",
  ])
}

resource "azurerm_key_vault_secret" "placeholders" {
  for_each = local.placeholder_secrets

  name         = each.value
  value        = "REPLACE_ME_${replace(each.value, "-", "_")}_via_az_keyvault_secret_set"
  key_vault_id = azurerm_key_vault.this.id
  tags         = var.tags

  lifecycle {
    # Prevent Terraform from overwriting secrets that have been rotated manually.
    ignore_changes = [value, version]
  }

  depends_on = [azurerm_role_assignment.terraform_kv_admin]
}
