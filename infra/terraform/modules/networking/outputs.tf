##########################################################################
# Module: networking — Outputs
#
# All cross-module wiring passes through these outputs.
# Consuming modules must declare corresponding input variables.
##########################################################################

output "vnet_id" {
  description = "Resource ID of the virtual network."
  value       = azurerm_virtual_network.this.id
}

output "vnet_name" {
  description = "Name of the virtual network."
  value       = azurerm_virtual_network.this.name
}

output "aks_nodes_subnet_id" {
  description = "Resource ID of the AKS node subnet."
  value       = azurerm_subnet.aks_nodes.id
}

output "aks_pods_subnet_id" {
  description = "Resource ID of the AKS pod subnet."
  value       = azurerm_subnet.aks_pods.id
}

output "private_endpoints_subnet_id" {
  description = "Resource ID of the private endpoints subnet."
  value       = azurerm_subnet.private_endpoints.id
}

output "postgres_delegated_subnet_id" {
  description = "Resource ID of the PostgreSQL Flexible Server delegated subnet."
  value       = azurerm_subnet.postgres_delegated.id
}

output "private_dns_zone_ids" {
  description = "Map of private DNS zone names to their resource IDs. Keys: postgres, redis, keyvault, acr."
  value = {
    for key, zone in azurerm_private_dns_zone.this : key => zone.id
  }
}

output "private_dns_zone_names" {
  description = "Map of private DNS zone keys to their FQDN zone names."
  value = {
    for key, zone in azurerm_private_dns_zone.this : key => zone.name
  }
}
