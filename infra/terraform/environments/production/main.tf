##########################################################################
# Root: environments/production — Module Orchestration
#
# Module call order (Terraform resolves via implicit deps, but shown here
# for clarity):
#   1. networking          — VNet, subnets, NSGs, private DNS zones
#   2. acr                 — Container registry (needed before AKS for AcrPull)
#   3. aks                 — Cluster + node pools + AcrPull role assignment
#   4. keyvault            — Key Vault + managed identities + federated creds
#      (needs AKS OIDC issuer URL)
#   5. postgres            — PostgreSQL Flexible Server
#   6. redis               — Azure Cache for Redis
#
# All cross-module wiring is explicit: outputs → variables.
# No module reads another module's resources via data sources.
##########################################################################

# ---------------------------------------------------------------------------
# Shared context — caller identity used for KV seeding RBAC
# ---------------------------------------------------------------------------
data "azurerm_client_config" "current" {}

# ---------------------------------------------------------------------------
# Resource Group — shared by all modules
# ---------------------------------------------------------------------------
resource "azurerm_resource_group" "main" {
  name     = "rg-${var.name_prefix}"
  location = var.location
  tags     = local.tags
}

locals {
  tags = merge(var.tags, {
    environment = var.environment
    managed_by  = "terraform"
  })
}

# ---------------------------------------------------------------------------
# 1. Networking
# ---------------------------------------------------------------------------
module "networking" {
  source = "../../modules/networking"

  resource_group_name            = azurerm_resource_group.main.name
  location                       = azurerm_resource_group.main.location
  name_prefix                    = var.name_prefix
  vnet_address_space             = var.vnet_address_space
  aks_nodes_subnet_cidr          = var.aks_nodes_subnet_cidr
  aks_pods_subnet_cidr           = var.aks_pods_subnet_cidr
  private_endpoints_subnet_cidr  = var.private_endpoints_subnet_cidr
  postgres_delegated_subnet_cidr = var.postgres_delegated_subnet_cidr
  tags                           = local.tags
}

# ---------------------------------------------------------------------------
# 2. Azure Container Registry
# (Created before AKS so its ID can be passed to the AKS module for AcrPull)
# ---------------------------------------------------------------------------
module "acr" {
  source = "../../modules/acr"

  resource_group_name         = azurerm_resource_group.main.name
  location                    = azurerm_resource_group.main.location
  name_prefix                 = var.name_prefix
  sku                         = var.acr_sku
  aks_nodes_subnet_id         = module.networking.aks_nodes_subnet_id
  private_endpoints_subnet_id = module.networking.private_endpoints_subnet_id
  private_dns_zone_id         = module.networking.private_dns_zone_ids["acr"]
  tags                        = local.tags
}

# ---------------------------------------------------------------------------
# 3. AKS Cluster
# Receives the ACR ID to create the AcrPull role assignment inside the module.
# ---------------------------------------------------------------------------
module "aks" {
  source = "../../modules/aks"

  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  name_prefix         = var.name_prefix
  kubernetes_version  = var.kubernetes_version
  aks_nodes_subnet_id = module.networking.aks_nodes_subnet_id
  aks_pods_subnet_id  = module.networking.aks_pods_subnet_id
  acr_id              = module.acr.registry_id

  system_pool = {
    vm_size    = var.system_pool_vm_size
    node_count = var.system_pool_node_count
  }

  app_pool = {
    vm_size   = var.app_pool_vm_size
    min_count = var.app_pool_min_count
    max_count = var.app_pool_max_count
  }

  gpu_pool = {
    vm_size   = var.gpu_pool_vm_size
    max_count = var.gpu_pool_max_count
  }

  tags = local.tags
}

# ---------------------------------------------------------------------------
# 4. Key Vault + Workload Identities
# Requires the AKS OIDC issuer URL for federated credential binding.
# ---------------------------------------------------------------------------
module "keyvault" {
  source = "../../modules/keyvault"

  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  name_prefix                = var.name_prefix
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  terraform_caller_object_id = data.azurerm_client_config.current.object_id
  oidc_issuer_url            = module.aks.oidc_issuer_url
  kubernetes_namespace       = var.kubernetes_namespace
  service_names              = var.service_names

  private_endpoints_subnet_id = module.networking.private_endpoints_subnet_id
  aks_nodes_subnet_id         = module.networking.aks_nodes_subnet_id
  private_dns_zone_id         = module.networking.private_dns_zone_ids["keyvault"]
  tags                        = local.tags
}

# ---------------------------------------------------------------------------
# 5. PostgreSQL Flexible Server
# Password is generated in the root (not in the module) so it is available
# here for the post-apply Key Vault seeding instruction in the output.
# ---------------------------------------------------------------------------
resource "random_password" "postgres" {
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

module "postgres" {
  source = "../../modules/postgres"

  resource_group_name    = azurerm_resource_group.main.name
  location               = azurerm_resource_group.main.location
  name_prefix            = var.name_prefix
  postgres_version       = var.postgres_version
  sku_name               = var.postgres_sku_name
  storage_mb             = var.postgres_storage_mb
  administrator_login    = var.postgres_admin_login
  administrator_password = random_password.postgres.result
  database_name          = var.postgres_database_name
  backup_retention_days  = var.postgres_backup_retention_days
  delegated_subnet_id    = module.networking.postgres_delegated_subnet_id
  private_dns_zone_id    = module.networking.private_dns_zone_ids["postgres"]
  tags                   = local.tags
}

# ---------------------------------------------------------------------------
# 6. Azure Cache for Redis
# ---------------------------------------------------------------------------
module "redis" {
  source = "../../modules/redis"

  resource_group_name         = azurerm_resource_group.main.name
  location                    = azurerm_resource_group.main.location
  name_prefix                 = var.name_prefix
  sku_name                    = var.redis_sku_name
  family                      = var.redis_family
  capacity                    = var.redis_capacity
  private_endpoints_subnet_id = module.networking.private_endpoints_subnet_id
  private_dns_zone_id         = module.networking.private_dns_zone_ids["redis"]
  tags                        = local.tags
}

# ---------------------------------------------------------------------------
# 7. Qdrant Backup — Azure Blob Storage
#
# Stores daily Qdrant vector snapshots created by the backup CronJob.
# The 'qdrant-backup' managed identity (created in the keyvault module via
# service_names) is granted 'Storage Blob Data Contributor' here.
#
# Storage account name must be globally unique and <= 24 lowercase alphanum.
# A random suffix ensures no collision on first apply.
# ---------------------------------------------------------------------------
resource "random_string" "backup_sa_suffix" {
  length  = 4
  upper   = false
  special = false
  numeric = true
}

resource "azurerm_storage_account" "qdrant_backup" {
  # Max 24 chars; name_prefix is typically <= 8 chars
  name                = "slm${var.name_prefix}bkp${random_string.backup_sa_suffix.result}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = local.tags

  account_tier             = "Standard"
  account_replication_type = "ZRS"   # Zone-redundant — survives AZ failure
  account_kind             = "StorageV2"
  access_tier              = "Cool"  # Snapshots are rarely read; Cool tier saves cost

  # Security hardening
  https_traffic_only_enabled      = true
  min_tls_version                 = "TLS1_2"
  shared_access_key_enabled       = false  # Force Azure AD auth; no storage keys
  default_to_oauth_authentication = true
  allow_nested_items_to_be_public = false
  public_network_access_enabled   = false  # Private access via subnet service endpoint

  blob_properties {
    # Soft-delete allows recovery of accidentally deleted snapshots within 7 days
    delete_retention_policy {
      days = 7
    }
    container_delete_retention_policy {
      days = 7
    }
  }

  network_rules {
    default_action             = "Deny"
    bypass                     = ["AzureServices"]
    virtual_network_subnet_ids = [module.networking.aks_nodes_subnet_id]
  }
}

resource "azurerm_storage_container" "qdrant_snapshots" {
  name                  = "qdrant-snapshots"
  storage_account_id    = azurerm_storage_account.qdrant_backup.id
  container_access_type = "private"
}

# Grant the qdrant-backup managed identity permission to upload blobs.
# 'Storage Blob Data Contributor' allows read/write/delete on blob data.
resource "azurerm_role_assignment" "qdrant_backup_sa" {
  scope                = azurerm_storage_account.qdrant_backup.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = module.keyvault.managed_identity_principal_ids["qdrant-backup"]
}
