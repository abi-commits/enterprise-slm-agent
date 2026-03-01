##########################################################################
# Module: keyvault — Input Variables
##########################################################################

variable "resource_group_name" {
  description = "Name of the resource group for Key Vault resources."
  type        = string
  nullable    = false
}

variable "location" {
  description = "Azure region for Key Vault resources."
  type        = string
  nullable    = false
}

variable "name_prefix" {
  description = "Short prefix for resource names (e.g. 'slm-prod')."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z0-9-]{3,20}$", var.name_prefix))
    error_message = "name_prefix must be 3–20 lowercase alphanumeric characters or hyphens."
  }
}

variable "tenant_id" {
  description = "Azure AD tenant ID. Typically sourced from data.azurerm_client_config.current.tenant_id in the root module."
  type        = string
  nullable    = false
}

variable "terraform_caller_object_id" {
  description = "Object ID of the identity running Terraform. Granted 'Key Vault Administrator' so it can seed placeholder secrets on first apply."
  type        = string
  nullable    = false
}

variable "oidc_issuer_url" {
  description = "OIDC issuer URL of the AKS cluster (from aks module). Required to create federated identity credentials for Workload Identity."
  type        = string
  nullable    = false
}

variable "kubernetes_namespace" {
  description = "Kubernetes namespace where service accounts for Workload Identity live."
  type        = string
  nullable    = false
  default     = "slm-prod"
}

variable "service_names" {
  description = "List of application service names to create managed identities and federated credentials for."
  type        = set(string)
  nullable    = false

  validation {
    condition     = length(var.service_names) > 0
    error_message = "service_names must contain at least one service."
  }
}

variable "private_endpoints_subnet_id" {
  description = "Resource ID of the private endpoints subnet where the Key Vault private endpoint will be created."
  type        = string
  nullable    = false
}

variable "aks_nodes_subnet_id" {
  description = "Resource ID of the AKS node subnet. Added to Key Vault network ACL for CSI driver access."
  type        = string
  nullable    = false
}

variable "private_dns_zone_id" {
  description = "Resource ID of the 'privatelink.vaultcore.azure.net' private DNS zone (from networking module)."
  type        = string
  nullable    = false
}

variable "tags" {
  description = "Map of tags to apply to all Key Vault resources."
  type        = map(string)
  nullable    = false
  default     = {}
}
