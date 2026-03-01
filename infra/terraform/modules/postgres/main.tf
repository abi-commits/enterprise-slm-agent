##########################################################################
# Module: postgres
#
# Provisions Azure Database for PostgreSQL Flexible Server with:
#   - Zone-redundant HA (primary + standby in separate AZs)
#   - Private networking (delegated subnet, no public access)
#   - 35-day PITR backup retention + geo-redundant backup
#   - Hardened server parameters (connection throttling, audit logging)
#
# The module outputs the server FQDN and computed connection string.
# The connection string MUST be stored in Key Vault by the operator after apply:
#   az keyvault secret set \
#     --vault-name <kv-name> \
#     --name postgres-connection-string \
#     --value "$(terraform output -raw postgres_connection_string)"
##########################################################################

resource "azurerm_postgresql_flexible_server" "this" {
  name                   = "psql-${var.name_prefix}"
  location               = var.location
  resource_group_name    = var.resource_group_name
  version                = var.postgres_version
  administrator_login    = var.administrator_login
  administrator_password = var.administrator_password
  sku_name               = var.sku_name
  storage_mb             = var.storage_mb
  tags                   = var.tags

  # Zone-redundant HA: a synchronous standby replica is maintained in a
  # different availability zone. Automatic failover in <120s on zone outage.
  high_availability {
    mode = "ZoneRedundant"
  }

  # Private networking only: server is unreachable from the public internet.
  delegated_subnet_id = var.delegated_subnet_id
  private_dns_zone_id = var.private_dns_zone_id

  backup_retention_days        = var.backup_retention_days
  geo_redundant_backup_enabled = true

  # Maintenance window: Sunday 02:00 UTC
  maintenance_window {
    day_of_week  = 0
    start_hour   = 2
    start_minute = 0
  }
}

# ---------------------------------------------------------------------------
# Application database
# ---------------------------------------------------------------------------
resource "azurerm_postgresql_flexible_server_database" "app" {
  name      = var.database_name
  server_id = azurerm_postgresql_flexible_server.this.id
  collation = "en_US.utf8"
  charset   = "UTF8"
}

# ---------------------------------------------------------------------------
# Server-level parameters — security hardening
# ---------------------------------------------------------------------------
resource "azurerm_postgresql_flexible_server_configuration" "connection_throttling" {
  name      = "connection_throttle.enable"
  server_id = azurerm_postgresql_flexible_server.this.id
  value     = "on"
}

resource "azurerm_postgresql_flexible_server_configuration" "log_connections" {
  name      = "log_connections"
  server_id = azurerm_postgresql_flexible_server.this.id
  value     = "on"
}

resource "azurerm_postgresql_flexible_server_configuration" "log_disconnections" {
  name      = "log_disconnections"
  server_id = azurerm_postgresql_flexible_server.this.id
  value     = "on"
}

resource "azurerm_postgresql_flexible_server_configuration" "log_checkpoints" {
  name      = "log_checkpoints"
  server_id = azurerm_postgresql_flexible_server.this.id
  value     = "on"
}
