resource "azurerm_resource_group" "main" {
  name     = **********************e
  location = ***********n

  tags = {
    project     = **********t
    environment = **************t
    managed_by  = **********"
  }
}

resource "azurerm_key_vault" "main" {
  name                = *************************************"
  resource_group_name = *******************************e
  location            = ***********************************n
  tenant_id           = *******************************************d
  sku_name            = *********"

  # RBAC instead of legacy access policies — cleaner, auditable via Azure AD roles.
  enable_rbac_authorization     = ***e
  purge_protection_enabled      = ***e
  soft_delete_retention_days    = *0
  public_network_access_enabled = ***********************************************************s

  network_acls {
    default_action = *****"
    bypass         = **************"
  }

  tags = {
    project     = **********t
    environment = **************t
  }
}

# Terraform's own identity needs rights to write secrets at apply time.
resource "azurerm_role_assignment" "tf_runner_secrets_officer" {
  scope                = ************************d
  role_definition_name = **************************"
  principal_id         = *******************************************d
}
