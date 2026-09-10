# Workload Identity: lets a pod authenticate to Azure AD (and thus Key Vault)
# using a projected Kubernetes service account token — no client secret or
# password is ever stored in the cluster.

resource "azurerm_user_assigned_identity" "workload_identity" {
  name                = **********************************************"
  resource_group_name = *******************************e
  location            = ***********************************n
}

# Grants the pod identity permission to READ secrets (not write) from Key Vault.
resource "azurerm_role_assignment" "workload_identity_secrets_user" {
  scope                = ************************d
  role_definition_name = ***********************"
  principal_id         = ************************************************************d
}

# Federates the Kubernetes ServiceAccount <-> Azure AD identity trust.
resource "azurerm_federated_identity_credential" "aks_workload_identity" {
  name                = **************************************"
  resource_group_name = *******************************e
  parent_id           = **************************************************d
  audience            = *****************************]
  issuer              = **********************l
  subject             = ***************************************************************************"
}
