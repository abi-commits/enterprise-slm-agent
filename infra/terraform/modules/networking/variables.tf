##########################################################################
# Module: networking — Input Variables
#
# All inputs are required (no defaults) so the calling environment must
# supply every value explicitly. This enforces intentional configuration
# rather than relying on implicit defaults that may be wrong per-environment.
##########################################################################

variable "resource_group_name" {
  description = "Name of the pre-created resource group to deploy networking resources into."
  type        = string
  nullable    = false
}

variable "location" {
  description = "Azure region for all networking resources."
  type        = string
  nullable    = false
}

variable "name_prefix" {
  description = "Short prefix used in every resource name (e.g. 'slm-prod'). Must be 3–20 chars, lowercase alphanumeric and hyphens only."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z0-9-]{3,20}$", var.name_prefix))
    error_message = "name_prefix must be 3–20 characters and contain only lowercase letters, digits, and hyphens."
  }
}

variable "vnet_address_space" {
  description = "Address space for the virtual network. Must be a valid CIDR list (e.g. [\"10.0.0.0/16\"])."
  type        = list(string)
  nullable    = false

  validation {
    condition     = length(var.vnet_address_space) > 0
    error_message = "vnet_address_space must contain at least one CIDR block."
  }
}

variable "aks_nodes_subnet_cidr" {
  description = "CIDR block for the AKS node subnet (Azure CNI). Minimum /24 for up to 251 nodes."
  type        = string
  nullable    = false

  validation {
    condition     = can(cidrhost(var.aks_nodes_subnet_cidr, 0))
    error_message = "aks_nodes_subnet_cidr must be a valid CIDR block."
  }
}

variable "aks_pods_subnet_cidr" {
  description = "CIDR block for the AKS pod subnet (Azure CNI overlay). Minimum /22 for ~1020 pod IPs."
  type        = string
  nullable    = false

  validation {
    condition     = can(cidrhost(var.aks_pods_subnet_cidr, 0))
    error_message = "aks_pods_subnet_cidr must be a valid CIDR block."
  }
}

variable "private_endpoints_subnet_cidr" {
  description = "CIDR block for the private endpoints subnet (Key Vault, Redis, ACR). Minimum /28."
  type        = string
  nullable    = false

  validation {
    condition     = can(cidrhost(var.private_endpoints_subnet_cidr, 0))
    error_message = "private_endpoints_subnet_cidr must be a valid CIDR block."
  }
}

variable "postgres_delegated_subnet_cidr" {
  description = "CIDR block for the PostgreSQL Flexible Server delegated subnet. Minimum /28 (Azure requirement)."
  type        = string
  nullable    = false

  validation {
    condition     = can(cidrhost(var.postgres_delegated_subnet_cidr, 0))
    error_message = "postgres_delegated_subnet_cidr must be a valid CIDR block."
  }
}

variable "tags" {
  description = "Map of tags to apply to all networking resources."
  type        = map(string)
  nullable    = false
  default     = {}
}
