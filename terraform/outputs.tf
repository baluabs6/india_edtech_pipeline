output "key_vault_name" {
  value = azurerm_key_vault.main.name
}

output "key_vault_uri" {
  value = azurerm_key_vault.main.vault_uri
}

output "workload_identity_client_id" {
  description = "Set as an annotation on the K8s ServiceAccount (azure.workload.identity/client-id)"
  value       = azurerm_user_assigned_identity.workload_identity.client_id
}

output "workload_identity_tenant_id" {
  value = data.azurerm_client_config.current.tenant_id
}

output "resource_group_name" {
  value = azurerm_resource_group.main.name
}
