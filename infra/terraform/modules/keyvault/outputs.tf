##########################################################################
# Module: keyvault — Outputs
##########################################################################

output "key_vault_id" {
  description = "Resource ID of the Key Vault."
  value       = azurerm_key_vault.this.id
}

output "key_vault_uri" {
  description = "URI of the Key Vault (e.g. https://kv-slm-prod-xxxx.vault.azure.net/)."
  value       = azurerm_key_vault.this.vault_uri
}

output "key_vault_name" {
  description = "Name of the Key Vault resource."
  value       = azurerm_key_vault.this.name
}

output "managed_identity_client_ids" {
  description = "Map of service name → Managed Identity client ID. Used to annotate Kubernetes ServiceAccounts for Workload Identity."
  value = {
    for name, mi in azurerm_user_assigned_identity.services : name => mi.client_id
  }
}

output "managed_identity_principal_ids" {
  description = "Map of service name → Managed Identity principal ID. Used for additional Azure RBAC assignments."
  value = {
    for name, mi in azurerm_user_assigned_identity.services : name => mi.principal_id
  }
}

output "managed_identity_ids" {
  description = "Map of service name → Managed Identity resource ID."
  value = {
    for name, mi in azurerm_user_assigned_identity.services : name => mi.id
  }
}
