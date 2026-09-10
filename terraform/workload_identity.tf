# Workload Identity: lets a pod authenticate to Azure AD (and thus Key Vault)
# using a projected Kubernetes service account token — no client secret or
# password is ever stored in the cluster.

resource "azurerm_user_assigned_identity" "workload_identity" {
  name                = "id-${var.project}-${var.environment}-workload"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
}

# Grants the pod identity permission to READ secrets (not write) from Key Vault.
resource "azurerm_role_assignment" "workload_identity_secrets_user" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.workload_identity.principal_id
}

# Federates the Kubernetes ServiceAccount <-> Azure AD identity trust.
resource "azurerm_federated_identity_credential" "aks_workload_identity" {
  name                = "fic-${var.project}-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  parent_id           = azurerm_user_assigned_identity.workload_identity.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = var.aks_oidc_issuer_url
  subject             = "system:serviceaccount:${var.k8s_namespace}:${var.k8s_service_account_name}"
}
