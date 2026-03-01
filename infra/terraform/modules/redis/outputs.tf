##########################################################################
# Module: redis — Outputs
##########################################################################

output "cache_id" {
  description = "Resource ID of the Azure Cache for Redis instance."
  value       = azurerm_redis_cache.this.id
}

output "hostname" {
  description = "Private endpoint hostname of the Redis cache (via Private DNS)."
  value       = azurerm_redis_cache.this.hostname
}

output "ssl_port" {
  description = "TLS port for Redis connections (always 6380)."
  value       = azurerm_redis_cache.this.ssl_port
}

output "primary_access_key" {
  description = "Primary access key for Redis. Sensitive — store in Key Vault after apply."
  value       = azurerm_redis_cache.this.primary_access_key
  sensitive   = true
}

output "connection_string" {
  description = <<-EOT
    TLS Redis DSN using the private endpoint hostname. Sensitive — store in Key Vault:
      az keyvault secret set --vault-name <kv> --name redis-connection-string --value "$(tf output -raw redis_connection_string)"
  EOT
  value     = "rediss://:${azurerm_redis_cache.this.primary_access_key}@${azurerm_redis_cache.this.hostname}:6380/0"
  sensitive = true
}
