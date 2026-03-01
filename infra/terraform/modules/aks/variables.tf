##########################################################################
# Module: aks — Input Variables
##########################################################################

variable "resource_group_name" {
  description = "Name of the resource group to deploy the AKS cluster into."
  type        = string
  nullable    = false
}

variable "location" {
  description = "Azure region for the AKS cluster and node pools."
  type        = string
  nullable    = false
}

variable "name_prefix" {
  description = "Short prefix used in all resource names (e.g. 'slm-prod')."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z0-9-]{3,20}$", var.name_prefix))
    error_message = "name_prefix must be 3–20 lowercase alphanumeric characters or hyphens."
  }
}

variable "kubernetes_version" {
  description = "AKS Kubernetes version. Must be a supported AKS version (e.g. '1.31')."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^\\d+\\.\\d+$", var.kubernetes_version))
    error_message = "kubernetes_version must be in 'MAJOR.MINOR' format (e.g. '1.31')."
  }
}

# ---------------------------------------------------------------------------
# Networking inputs (from networking module outputs)
# ---------------------------------------------------------------------------
variable "aks_nodes_subnet_id" {
  description = "Resource ID of the AKS node subnet (from networking module)."
  type        = string
  nullable    = false
}

variable "aks_pods_subnet_id" {
  description = "Resource ID of the AKS pod subnet (from networking module)."
  type        = string
  nullable    = false
}

# ---------------------------------------------------------------------------
# System node pool
# ---------------------------------------------------------------------------
variable "system_pool" {
  description = "Configuration for the system node pool ('systempool'). Runs cluster system add-ons only."
  type = object({
    vm_size    = string
    node_count = number
  })
  nullable = false

  validation {
    condition     = var.system_pool.node_count >= 3
    error_message = "system_pool.node_count must be at least 3 for zone-redundant HA."
  }
}

# ---------------------------------------------------------------------------
# Application node pool
# ---------------------------------------------------------------------------
variable "app_pool" {
  description = "Configuration for the application node pool ('apppool'). Runs api, knowledge, inference, and qdrant workloads."
  type = object({
    vm_size   = string
    min_count = number
    max_count = number
  })
  nullable = false

  validation {
    condition     = var.app_pool.min_count >= 2 && var.app_pool.max_count >= var.app_pool.min_count
    error_message = "app_pool.min_count must be >= 2 and max_count must be >= min_count."
  }
}

# ---------------------------------------------------------------------------
# GPU node pool
# ---------------------------------------------------------------------------
variable "gpu_pool" {
  description = "Configuration for the GPU node pool ('gpupool'). Runs vLLM. Set max_count=0 to disable."
  type = object({
    vm_size   = string
    max_count = number
  })
  nullable = false

  validation {
    condition     = var.gpu_pool.max_count >= 0
    error_message = "gpu_pool.max_count must be >= 0."
  }
}

# ---------------------------------------------------------------------------
# RBAC / ACR
# ---------------------------------------------------------------------------
variable "acr_id" {
  description = "Resource ID of the Azure Container Registry. Used to grant AcrPull to the kubelet identity."
  type        = string
  nullable    = false
}

variable "tags" {
  description = "Map of tags to apply to all AKS resources."
  type        = map(string)
  nullable    = false
  default     = {}
}
