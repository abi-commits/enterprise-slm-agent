##########################################################################
# Module: acr — Input Variables
##########################################################################

variable "resource_group_name" {
  description = "Name of the resource group for the container registry."
  type        = string
  nullable    = false
}

variable "location" {
  description = "Azure region for the container registry."
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

variable "sku" {
  description = "ACR SKU. Must be 'Premium' — required for private link, content trust, and network rules."
  type        = string
  nullable    = false
  default     = "Premium"

  validation {
    condition     = var.sku == "Premium"
    error_message = "ACR SKU must be 'Premium' to support private endpoints and content trust."
  }
}

variable "aks_nodes_subnet_id" {
  description = "Resource ID of the AKS node subnet. Added to the ACR network allow-list so nodes can pull images."
  type        = string
  nullable    = false
}

variable "private_endpoints_subnet_id" {
  description = "Resource ID of the private endpoints subnet where the ACR private endpoint will be created."
  type        = string
  nullable    = false
}

variable "private_dns_zone_id" {
  description = "Resource ID of the 'privatelink.azurecr.io' private DNS zone (from networking module)."
  type        = string
  nullable    = false
}

variable "tags" {
  description = "Map of tags to apply to all ACR resources."
  type        = map(string)
  nullable    = false
  default     = {}
}
