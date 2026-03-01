##########################################################################
# Root: environments/production — Terraform & Provider Configuration
#
# This is the only place where provider blocks and the backend live.
# Modules must never contain provider blocks.
##########################################################################

terraform {
  required_version = ">= 1.7.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.110"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 2.53"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Remote state stored in Azure Blob Storage.
  # Provision the storage account once before running `terraform init`:
  #
  #   az group create -n rg-slm-tfstate -l uksouth
  #   az storage account create \
  #     -n <storage_account_name> -g rg-slm-tfstate --sku Standard_LRS \
  #     --allow-blob-public-access false --min-tls-version TLS1_2
  #   az storage container create -n tfstate --account-name <storage_account_name>
  #
  # Then initialise:
  #   terraform init \
  #     -backend-config="storage_account_name=<storage_account_name>" \
  #     -backend-config="access_key=$(az storage account keys list ...)"
  backend "azurerm" {
    resource_group_name  = "rg-slm-tfstate"
    storage_account_name = "slmtfstate" # override via -backend-config
    container_name       = "tfstate"
    key                  = "environments/production.terraform.tfstate"
  }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy    = false # Retain soft-deleted KVs for audit trail
      recover_soft_deleted_key_vaults = true
    }
    resource_group {
      # Prevent accidental deletion of non-empty resource groups
      prevent_deletion_if_contains_resources = true
    }
  }
}

provider "azuread" {}
provider "random" {}
