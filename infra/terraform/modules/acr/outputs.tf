##########################################################################
# Module: acr — Outputs
##########################################################################

output "registry_id" {
  description = "Resource ID of the container registry. Used by the aks module to grant AcrPull."
  value       = azurerm_container_registry.this.id
}

output "login_server" {
  description = "Login server FQDN of the container registry (e.g. slmprodacr1234.azurecr.io)."
  value       = azurerm_container_registry.this.login_server
}

output "registry_name" {
  description = "Name of the container registry resource."
  value       = azurerm_container_registry.this.name
}
