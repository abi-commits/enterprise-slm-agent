##########################################################################
# Module: redis — Input Variables
##########################################################################

variable "resource_group_name" {
  description = "Name of the resource group for Redis Cache resources."
  type        = string
  nullable    = false
}

variable "location" {
  description = "Azure region for the Redis Cache instance."
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

variable "sku_name" {
  description = "Redis Cache SKU. 'Standard' or 'Premium'. Premium supports VNet injection; Standard uses private endpoint."
  type        = string
  nullable    = false
  default     = "Standard"

  validation {
    condition     = contains(["Basic", "Standard", "Premium"], var.sku_name)
    error_message = "sku_name must be one of: 'Basic', 'Standard', 'Premium'."
  }
}

variable "family" {
  description = "Redis Cache family. 'C' for Basic/Standard (C0–C6), 'P' for Premium (P1–P5)."
  type        = string
  nullable    = false

  validation {
    condition     = contains(["C", "P"], var.family)
    error_message = "family must be 'C' (Basic/Standard) or 'P' (Premium)."
  }
}

variable "capacity" {
  description = "Redis Cache capacity (size). For Standard C-family: 0=250MB 1=1GB 2=6GB 3=13GB 4=26GB 5=53GB 6=53GB."
  type        = number
  nullable    = false

  validation {
    condition     = var.capacity >= 0 && var.capacity <= 6
    error_message = "capacity must be between 0 and 6."
  }
}

variable "private_endpoints_subnet_id" {
  description = "Resource ID of the private endpoints subnet where the Redis private endpoint is created."
  type        = string
  nullable    = false
}

variable "private_dns_zone_id" {
  description = "Resource ID of the 'privatelink.redis.cache.windows.net' private DNS zone (from networking module)."
  type        = string
  nullable    = false
}

variable "tags" {
  description = "Map of tags to apply to all Redis resources."
  type        = map(string)
  nullable    = false
  default     = {}
}
