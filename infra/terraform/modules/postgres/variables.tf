##########################################################################
# Module: postgres — Input Variables
##########################################################################

variable "resource_group_name" {
  description = "Name of the resource group for PostgreSQL resources."
  type        = string
  nullable    = false
}

variable "location" {
  description = "Azure region for the PostgreSQL Flexible Server."
  type        = string
  nullable    = false
}

variable "name_prefix" {
  description = "Short prefix for resource names (e.g. 'athena-prod')."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z0-9-]{3,20}$", var.name_prefix))
    error_message = "name_prefix must be 3–20 lowercase alphanumeric characters or hyphens."
  }
}

variable "postgres_version" {
  description = "PostgreSQL major version. Supported values: '14', '15', '16'."
  type        = string
  nullable    = false
  default     = "16"

  validation {
    condition     = contains(["14", "15", "16"], var.postgres_version)
    error_message = "postgres_version must be one of: '14', '15', '16'."
  }
}

variable "sku_name" {
  description = "PostgreSQL Flexible Server SKU (e.g. 'GP_Standard_D4s_v3'). GP_ prefix required for zone-redundant HA."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^GP_", var.sku_name))
    error_message = "sku_name must be a General Purpose SKU starting with 'GP_' to support zone-redundant HA."
  }
}

variable "storage_mb" {
  description = "Storage capacity in MB. Minimum 32768 (32 GB); must be a multiple of 1024."
  type        = number
  nullable    = false
  default     = 32768

  validation {
    condition     = var.storage_mb >= 32768 && var.storage_mb % 1024 == 0
    error_message = "storage_mb must be at least 32768 and a multiple of 1024."
  }
}

variable "administrator_login" {
  description = "Administrator username for the PostgreSQL server. Cannot be 'azure_superuser', 'admin', 'administrator', 'root', 'guest', or 'public'."
  type        = string
  nullable    = false

  validation {
    condition     = !contains(["azure_superuser", "admin", "administrator", "root", "guest", "public"], var.administrator_login)
    error_message = "administrator_login must not be a reserved PostgreSQL username."
  }
}

variable "administrator_password" {
  description = "Administrator password. Must be at least 8 chars with uppercase, lowercase, digit, and special character."
  type        = string
  nullable    = false
  sensitive   = true
}

variable "database_name" {
  description = "Name of the application database to create."
  type        = string
  nullable    = false
  default     = "athena_knowledge"
}

variable "backup_retention_days" {
  description = "Number of days to retain PITR backups. Range: 7–35."
  type        = number
  nullable    = false
  default     = 35

  validation {
    condition     = var.backup_retention_days >= 7 && var.backup_retention_days <= 35
    error_message = "backup_retention_days must be between 7 and 35."
  }
}

variable "delegated_subnet_id" {
  description = "Resource ID of the PostgreSQL-delegated subnet (from networking module)."
  type        = string
  nullable    = false
}

variable "private_dns_zone_id" {
  description = "Resource ID of the 'privatelink.postgres.database.azure.com' private DNS zone (from networking module)."
  type        = string
  nullable    = false
}

variable "tags" {
  description = "Map of tags to apply to all PostgreSQL resources."
  type        = map(string)
  nullable    = false
  default     = {}
}
