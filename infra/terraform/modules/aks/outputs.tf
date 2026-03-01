##########################################################################
# Module: aks — Outputs
##########################################################################

output "cluster_id" {
  description = "Resource ID of the AKS cluster."
  value       = azurerm_kubernetes_cluster.this.id
}

output "cluster_name" {
  description = "Name of the AKS cluster."
  value       = azurerm_kubernetes_cluster.this.name
}

output "cluster_fqdn" {
  description = "FQDN of the AKS API server."
  value       = azurerm_kubernetes_cluster.this.fqdn
}

output "oidc_issuer_url" {
  description = "OIDC issuer URL for Workload Identity federation."
  value       = azurerm_kubernetes_cluster.this.oidc_issuer_url
}

output "kubelet_identity_object_id" {
  description = "Object ID of the kubelet managed identity (used for AcrPull and other role assignments)."
  value       = azurerm_kubernetes_cluster.this.kubelet_identity[0].object_id
}

output "control_plane_identity_principal_id" {
  description = "Principal ID of the cluster's system-assigned managed identity."
  value       = azurerm_kubernetes_cluster.this.identity[0].principal_id
}

output "kube_config_raw" {
  description = "Raw kubeconfig for the AKS cluster. Sensitive — store securely and never log."
  value       = azurerm_kubernetes_cluster.this.kube_config_raw
  sensitive   = true
}
