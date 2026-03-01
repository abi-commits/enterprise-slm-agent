##########################################################################
# Module: postgres — Outputs
##########################################################################

output "server_fqdn" {
  description = "Fully qualified domain name of the PostgreSQL Flexible Server (private endpoint FQDN)."
  value       = azurerm_postgresql_flexible_server.this.fqdn
}

output "server_id" {
  description = "Resource ID of the PostgreSQL Flexible Server."
  value       = azurerm_postgresql_flexible_server.this.id
}

output "database_name" {
  description = "Name of the application database created on the server."
  value       = azurerm_postgresql_flexible_server_database.app.name
}

output "connection_string" {
  description = <<-EOT
    Full asyncpg DSN for the application services. Sensitive — store in Azure Key Vault:
      az keyvault secret set --vault-name <kv> --name postgres-connection-string --value "$(tf output -raw postgres_connection_string)"
  EOT
  value = "postgresql+asyncpg://${var.administrator_login}:${var.administrator_password}@${azurerm_postgresql_flexible_server.this.fqdn}:5432/${azurerm_postgresql_flexible_server_database.app.name}?ssl=require"
  sensitive = true
}
