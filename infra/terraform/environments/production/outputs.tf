##########################################################################
# Root: environments/production — Outputs
#
# These outputs surface the key resource IDs and FQDNs needed to:
#   - Configure kubectl (kube_config)
#   - Seed Key Vault secrets post-apply
#   - Build and push images to ACR
#   - Configure Kubernetes manifests / Helm values
#
# Sensitive outputs are marked sensitive=true and will not print without
# `terraform output -raw <name>`.
##########################################################################

# ---------------------------------------------------------------------------
# Resource Group
# ---------------------------------------------------------------------------
output "resource_group_name" {
  description = "Name of the resource group containing all production resources."
  value       = azurerm_resource_group.main.name
}

# ---------------------------------------------------------------------------
# Networking
# ---------------------------------------------------------------------------
output "vnet_id" {
  description = "Resource ID of the production virtual network."
  value       = module.networking.vnet_id
}

# ---------------------------------------------------------------------------
# AKS
# ---------------------------------------------------------------------------
output "aks_cluster_name" {
  description = "Name of the AKS cluster. Used with: az aks get-credentials -n <name> -g <rg>"
  value       = module.aks.cluster_name
}

output "aks_oidc_issuer_url" {
  description = "AKS OIDC issuer URL. Used to verify Workload Identity federated credentials."
  value       = module.aks.oidc_issuer_url
}

output "kube_config" {
  description = "Raw kubeconfig for the AKS cluster. Run: terraform output -raw kube_config > ~/.kube/config"
  value       = module.aks.kube_config_raw
  sensitive   = true
}

# ---------------------------------------------------------------------------
# ACR
# ---------------------------------------------------------------------------
output "acr_login_server" {
  description = "ACR login server FQDN. Used to tag and push images: docker push <login_server>/slm/<service>:<tag>"
  value       = module.acr.login_server
}

# ---------------------------------------------------------------------------
# Key Vault
# ---------------------------------------------------------------------------
output "key_vault_name" {
  description = "Name of the Key Vault. Used with az keyvault secret set to seed real secret values after apply."
  value       = module.keyvault.key_vault_name
}

output "key_vault_uri" {
  description = "URI of the Key Vault. Used in SecretProviderClass manifests."
  value       = module.keyvault.key_vault_uri
}

output "managed_identity_client_ids" {
  description = "Map of service name → Managed Identity client ID. Use these to annotate Kubernetes ServiceAccounts."
  value       = module.keyvault.managed_identity_client_ids
}

# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------
output "postgres_fqdn" {
  description = "PostgreSQL Flexible Server FQDN (private endpoint). Informational — do not put in app config directly; use Key Vault."
  value       = module.postgres.server_fqdn
}

output "postgres_connection_string" {
  description = <<-EOT
    Full asyncpg connection string. After apply, seed into Key Vault:
      az keyvault secret set \
        --vault-name $(terraform output -raw key_vault_name) \
        --name postgres-connection-string \
        --value "$(terraform output -raw postgres_connection_string)"
  EOT
  value     = module.postgres.connection_string
  sensitive = true
}

# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------
output "redis_hostname" {
  description = "Hostname of the Redis private endpoint. Informational."
  value       = module.redis.hostname
}

output "redis_connection_string" {
  description = <<-EOT
    TLS Redis connection string. After apply, seed into Key Vault:
      az keyvault secret set \
        --vault-name $(terraform output -raw key_vault_name) \
        --name redis-connection-string \
        --value "$(terraform output -raw redis_connection_string)"
  EOT
  value     = module.redis.connection_string
  sensitive = true
}

# ---------------------------------------------------------------------------
# Qdrant Backup Storage
# ---------------------------------------------------------------------------
output "qdrant_backup_storage_account" {
  description = "Name of the Azure Storage Account used for Qdrant snapshot backups."
  value       = azurerm_storage_account.qdrant_backup.name
}

output "qdrant_backup_container" {
  description = "Name of the Blob container that stores Qdrant snapshots."
  value       = azurerm_storage_container.qdrant_snapshots.name
}

# ---------------------------------------------------------------------------
# Post-apply instructions
# ---------------------------------------------------------------------------
output "next_steps" {
  description = "Ordered steps to complete the production setup after terraform apply."
  value       = <<-EOT

    ============================================================
    POST-APPLY STEPS
    ============================================================
    1. Get cluster credentials:
       az aks get-credentials \
         --name ${module.aks.cluster_name} \
         --resource-group ${azurerm_resource_group.main.name}

    2. Seed Key Vault secrets (run each command):
       KV=${module.keyvault.key_vault_name}

       # JWT secret (generate a 256-bit key):
       az keyvault secret set --vault-name $KV --name jwt-secret-key \
         --value "$(openssl rand -hex 32)"

       # PostgreSQL connection string:
       az keyvault secret set --vault-name $KV --name postgres-connection-string \
         --value "$(terraform output -raw postgres_connection_string)"

       # Redis connection string:
       az keyvault secret set --vault-name $KV --name redis-connection-string \
         --value "$(terraform output -raw redis_connection_string)"

       # Alert webhook (Slack/Teams):
       az keyvault secret set --vault-name $KV --name alert-webhook-url \
         --value "<your-webhook-url>"

       # HuggingFace token (for gated models):
       az keyvault secret set --vault-name $KV --name huggingface-hub-token \
         --value "hf_..."

    3. Tag and push images to ACR:
       az acr login --name ${module.acr.login_server}
       docker tag slm-api-service:latest \
         ${module.acr.login_server}/slm/api-service:<git-sha>

    4. Deploy Helm charts:
       # Update values-production.yaml with backup storage account name:
       #   qdrant.backup.storageAccountName: $(terraform output -raw qdrant_backup_storage_account)

       helm upgrade --install enterprise-slm ./helm/enterprise-slm \
         -f helm/enterprise-slm/values-production.yaml \
         --namespace slm-prod --create-namespace

       # Deploy observability stack:
       cd helm/observability && ./deploy.sh

    5. Validate GPU node pool activation (when GPU nodes are needed):
       kubectl get nodes -l agentpool=gpupool
    ============================================================
  EOT
}
