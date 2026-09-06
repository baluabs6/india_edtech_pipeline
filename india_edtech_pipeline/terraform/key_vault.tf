resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location

  tags = {
    project     = var.project
    environment = var.environment
    managed_by  = "terraform"
  }
}

resource "azurerm_key_vault" "main" {
  name                = "kv-${var.project}-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"

  # RBAC instead of legacy access policies — cleaner, auditable via Azure AD roles.
  enable_rbac_authorization     = true
  purge_protection_enabled      = true
  soft_delete_retention_days    = 90
  public_network_access_enabled = false # force access via private endpoint / trusted services

  network_acls {
    default_action = "Deny"
    bypass         = "AzureServices"
  }

  tags = {
    project     = var.project
    environment = var.environment
  }
}

# Terraform's own identity needs rights to write secrets at apply time.
resource "azurerm_role_assignment" "tf_runner_secrets_officer" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}
