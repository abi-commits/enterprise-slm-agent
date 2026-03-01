##########################################################################
# Module: redis
#
# Provisions Azure Cache for Redis with:
#   - TLS-only (port 6379 disabled; port 6380 TLS enforced)
#   - RDB + AOF persistence for ingestion queue durability
#   - Public access disabled; private endpoint for in-VNet access only
#   - allkeys-lru eviction policy (cache + queue hybrid workload)
#
# The connection string output MUST be stored in Key Vault after apply:
#   az keyvault secret set \
#     --vault-name <kv-name> \
#     --name redis-connection-string \
#     --value "$(terraform output -raw redis_connection_string)"
##########################################################################

resource "azurerm_redis_cache" "this" {
  name                = "redis-${var.name_prefix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  capacity            = var.capacity
  family              = var.family
  sku_name            = var.sku_name
  tags                = var.tags

  # Disable plaintext port 6379; enforce TLS 1.2 on port 6380.
  enable_non_ssl_port = false
  minimum_tls_version = "1.2"

  redis_configuration {
    # RDB snapshots every 60 minutes + AOF for durability of Redis Streams
    # (ingestion queue). If the instance is recycled, in-flight ingestion
    # jobs survive.
    rdb_backup_enabled            = true
    rdb_backup_frequency          = 60
    rdb_backup_max_snapshot_count = 1
    aof_backup_enabled            = true

    # allkeys-lru: evict least-recently-used keys when memory is full.
    # Appropriate for a mixed cache + queue workload where cache misses
    # are acceptable but queue entries are protected by AOF persistence.
    maxmemory_policy = "allkeys-lru"

    # Keyspace notifications for Redis Streams monitoring
    # (lets Prometheus consumer track queue depth via XLEN).
    notify_keyspace_events = "KEA"
  }

  # Patch window: Sunday 23:00 UTC to avoid business-hours disruption.
  patch_schedule {
    day_of_week    = "Sunday"
    start_hour_utc = 23
  }
}

# ---------------------------------------------------------------------------
# Private Endpoint — Redis only reachable from within the VNet
# ---------------------------------------------------------------------------
resource "azurerm_private_endpoint" "redis" {
  name                = "pe-redis-${var.name_prefix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.private_endpoints_subnet_id
  tags                = var.tags

  private_service_connection {
    name                           = "psc-redis-${var.name_prefix}"
    private_connection_resource_id = azurerm_redis_cache.this.id
    subresource_names              = ["redisCache"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "redis-dns-zone-group"
    private_dns_zone_ids = [var.private_dns_zone_id]
  }
}
