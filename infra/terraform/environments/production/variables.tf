##########################################################################
# Root: environments/production — Variables
#
# Non-secret values are set in terraform.tfvars.
# Sensitive values (passwords, tokens) are supplied via environment variables:
#   export TF_VAR_postgres_admin_password="..."
##########################################################################

# ---------------------------------------------------------------------------
# Global
# ---------------------------------------------------------------------------
variable "location" {
  description = "Azure region for all resources."
  type        = string

  validation {
    condition     = length(var.location) > 0
    error_message = "location must not be empty."
  }
}

variable "environment" {
  description = "Deployment environment label used in tags (e.g. 'production', 'staging')."
  type        = string

  validation {
    condition     = contains(["production", "staging", "development"], var.environment)
    error_message = "environment must be one of: 'production', 'staging', 'development'."
  }
}

variable "name_prefix" {
  description = "Short globally-unique prefix for all resource names (e.g. 'slm-prod'). 3–20 lowercase alphanumeric + hyphens."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9-]{3,20}$", var.name_prefix))
    error_message = "name_prefix must be 3–20 lowercase alphanumeric characters or hyphens."
  }
}

variable "tags" {
  description = "Additional tags to merge into all resources."
  type        = map(string)
  default     = {}
}

# ---------------------------------------------------------------------------
# Networking
# ---------------------------------------------------------------------------
variable "vnet_address_space" {
  description = "Address space for the virtual network (e.g. [\"10.0.0.0/16\"])."
  type        = list(string)
}

variable "aks_nodes_subnet_cidr" {
  description = "CIDR for the AKS node subnet. Minimum /24."
  type        = string

  validation {
    condition     = can(cidrhost(var.aks_nodes_subnet_cidr, 0))
    error_message = "aks_nodes_subnet_cidr must be a valid CIDR block."
  }
}

variable "aks_pods_subnet_cidr" {
  description = "CIDR for the AKS pod subnet. Minimum /22 (~1020 pod IPs)."
  type        = string

  validation {
    condition     = can(cidrhost(var.aks_pods_subnet_cidr, 0))
    error_message = "aks_pods_subnet_cidr must be a valid CIDR block."
  }
}

variable "private_endpoints_subnet_cidr" {
  description = "CIDR for the private endpoints subnet. Minimum /28."
  type        = string

  validation {
    condition     = can(cidrhost(var.private_endpoints_subnet_cidr, 0))
    error_message = "private_endpoints_subnet_cidr must be a valid CIDR block."
  }
}

variable "postgres_delegated_subnet_cidr" {
  description = "CIDR for the PostgreSQL Flexible Server delegated subnet. Minimum /28 (Azure requirement)."
  type        = string

  validation {
    condition     = can(cidrhost(var.postgres_delegated_subnet_cidr, 0))
    error_message = "postgres_delegated_subnet_cidr must be a valid CIDR block."
  }
}

# ---------------------------------------------------------------------------
# AKS
# ---------------------------------------------------------------------------
variable "kubernetes_version" {
  description = "AKS Kubernetes version in MAJOR.MINOR format (e.g. '1.31')."
  type        = string

  validation {
    condition     = can(regex("^\\d+\\.\\d+$", var.kubernetes_version))
    error_message = "kubernetes_version must be in 'MAJOR.MINOR' format."
  }
}

variable "system_pool_vm_size" {
  description = "VM SKU for the system node pool (e.g. 'Standard_D4s_v3')."
  type        = string
}

variable "system_pool_node_count" {
  description = "Fixed node count for system pool. Minimum 3 for zone-redundant HA."
  type        = number

  validation {
    condition     = var.system_pool_node_count >= 3
    error_message = "system_pool_node_count must be at least 3."
  }
}

variable "app_pool_vm_size" {
  description = "VM SKU for the application node pool (e.g. 'Standard_D8s_v4')."
  type        = string
}

variable "app_pool_min_count" {
  description = "Minimum autoscaler node count for the app pool. Minimum 2."
  type        = number

  validation {
    condition     = var.app_pool_min_count >= 2
    error_message = "app_pool_min_count must be at least 2."
  }
}

variable "app_pool_max_count" {
  description = "Maximum autoscaler node count for the app pool."
  type        = number
}

variable "gpu_pool_vm_size" {
  description = "VM SKU for the GPU node pool (e.g. 'Standard_NC6s_v3'). Requires NVIDIA GPU SKU."
  type        = string
}

variable "gpu_pool_max_count" {
  description = "Maximum node count for the GPU pool. Set to 0 to provision pool but keep at zero until vLLM is activated."
  type        = number
}

# ---------------------------------------------------------------------------
# ACR
# ---------------------------------------------------------------------------
variable "acr_sku" {
  description = "Azure Container Registry SKU. Must be 'Premium' for private link."
  type        = string
  default     = "Premium"

  validation {
    condition     = var.acr_sku == "Premium"
    error_message = "acr_sku must be 'Premium' to support private endpoints."
  }
}

# ---------------------------------------------------------------------------
# Key Vault & Workload Identity
# ---------------------------------------------------------------------------
variable "kubernetes_namespace" {
  description = "Kubernetes namespace for application workloads. Used in federated identity credential subject."
  type        = string
  default     = "slm-prod"
}

variable "service_names" {
  description = "Set of service names for which managed identities and federated credentials are created."
  type        = set(string)
  default     = ["api-service", "knowledge-service", "inference-service", "alembic-job", "qdrant-backup"]
}

# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------
variable "postgres_version" {
  description = "PostgreSQL major version ('14', '15', or '16')."
  type        = string
  default     = "16"
}

variable "postgres_sku_name" {
  description = "PostgreSQL SKU including tier prefix (e.g. 'GP_Standard_D4s_v3'). Must start with 'GP_' for HA."
  type        = string

  validation {
    condition     = can(regex("^GP_", var.postgres_sku_name))
    error_message = "postgres_sku_name must be a General Purpose ('GP_') SKU."
  }
}

variable "postgres_storage_mb" {
  description = "PostgreSQL storage in MB. Minimum 32768 (32 GB)."
  type        = number
  default     = 32768
}

variable "postgres_admin_login" {
  description = "PostgreSQL administrator username."
  type        = string
  default     = "slm_admin"

  validation {
    condition     = !contains(["admin", "administrator", "root", "guest", "public", "azure_superuser"], var.postgres_admin_login)
    error_message = "postgres_admin_login must not be a reserved PostgreSQL username."
  }
}

variable "postgres_database_name" {
  description = "Name of the application database to create."
  type        = string
  default     = "slm_knowledge"
}

variable "postgres_backup_retention_days" {
  description = "PITR backup retention days (7–35)."
  type        = number
  default     = 35

  validation {
    condition     = var.postgres_backup_retention_days >= 7 && var.postgres_backup_retention_days <= 35
    error_message = "postgres_backup_retention_days must be between 7 and 35."
  }
}

# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------
variable "redis_sku_name" {
  description = "Redis Cache SKU name ('Basic', 'Standard', or 'Premium')."
  type        = string
  default     = "Standard"
}

variable "redis_family" {
  description = "Redis Cache family ('C' for Basic/Standard, 'P' for Premium)."
  type        = string
  default     = "C"
}

variable "redis_capacity" {
  description = "Redis Cache capacity size (0–6)."
  type        = number
  default     = 2

  validation {
    condition     = var.redis_capacity >= 0 && var.redis_capacity <= 6
    error_message = "redis_capacity must be between 0 and 6."
  }
}
