resource "azurerm_key_vault_secret" "pg_host" {
  name         = "PG-HOST"
  value        = var.pg_host
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.tf_runner_secrets_officer]
}

resource "azurerm_key_vault_secret" "pg_user" {
  name         = "PG-USER"
  value        = var.pg_user
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.tf_runner_secrets_officer]
}

resource "azurerm_key_vault_secret" "pg_password" {
  name         = "PG-PASSWORD"
  value        = var.pg_admin_password
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.tf_runner_secrets_officer]
}

resource "azurerm_key_vault_secret" "mongo_uri" {
  name         = "MONGO-URI"
  value        = var.mongo_connection_string
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.tf_runner_secrets_officer]
}

resource "azurerm_key_vault_secret" "azure_openai_endpoint" {
  name         = "AZURE-OPENAI-ENDPOINT"
  value        = var.azure_openai_endpoint
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.tf_runner_secrets_officer]
}

resource "azurerm_key_vault_secret" "azure_openai_api_key" {
  name         = "AZURE-OPENAI-API-KEY"
  value        = var.azure_openai_api_key
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.tf_runner_secrets_officer]
}

resource "azurerm_key_vault_secret" "api_key" {
  name         = "API-KEY"
  value        = var.api_key
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.tf_runner_secrets_officer]
}

resource "azurerm_key_vault_secret" "azure_language_endpoint" {
  name         = "AZURE-LANGUAGE-ENDPOINT"
  value        = var.azure_language_endpoint
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.tf_runner_secrets_officer]
}

resource "azurerm_key_vault_secret" "azure_language_key" {
  name         = "AZURE-LANGUAGE-KEY"
  value        = var.azure_language_key
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.tf_runner_secrets_officer]
}

resource "azurerm_key_vault_secret" "whatsapp_verify_token" {
  name         = "WHATSAPP-VERIFY-TOKEN"
  value        = var.whatsapp_verify_token
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.tf_runner_secrets_officer]
}

resource "azurerm_key_vault_secret" "whatsapp_access_token" {
  name         = "WHATSAPP-ACCESS-TOKEN"
  value        = var.whatsapp_access_token
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.tf_runner_secrets_officer]
}

resource "azurerm_key_vault_secret" "whatsapp_phone_number_id" {
  name         = "WHATSAPP-PHONE-NUMBER-ID"
  value        = var.whatsapp_phone_number_id
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.tf_runner_secrets_officer]
}

resource "azurerm_key_vault_secret" "whatsapp_app_secret" {
  name         = "WHATSAPP-APP-SECRET"
  value        = var.whatsapp_app_secret
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.tf_runner_secrets_officer]
}

resource "azurerm_key_vault_secret" "jwt_secret" {
  name         = "JWT-SECRET"
  value        = var.jwt_secret
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.tf_runner_secrets_officer]
}

resource "azurerm_key_vault_secret" "export_hash_secret" {
  # Keyed-hash secret for pseudonymizing student_id in /v1/export/anonymized.
  # Deliberately a distinct secret from JWT-SECRET (see config.py) so
  # rotating one never silently rotates, and re-identifies past exports
  # under, the other.
  name         = "EXPORT-HASH-SECRET"
  value        = var.export_hash_secret
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.tf_runner_secrets_officer]
}

resource "azurerm_key_vault_secret" "client_credentials_json" {
  name         = "CLIENT-CREDENTIALS-JSON"
  value        = var.client_credentials_json
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.tf_runner_secrets_officer]
}

resource "azurerm_key_vault_secret" "smtp_password" {
  count        = var.smtp_password != "" ? 1 : 0
  name         = "SMTP-PASSWORD"
  value        = var.smtp_password
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.tf_runner_secrets_officer]
}

resource "azurerm_key_vault_secret" "smtp_config" {
  for_each = {
    "SMTP-HOST"        = var.smtp_host
    "SMTP-USER"        = var.smtp_user
    "ALERT-FROM-EMAIL" = var.alert_from_email
    "ALERT-TO-EMAILS"  = var.alert_to_emails
  }
  name         = each.key
  value        = each.value
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.tf_runner_secrets_officer]
}

# NOTE: no secret value is ever written to a .tf file, tfvars committed to
# git, plan output, or Kubernetes YAML. They flow: CI secret store ->
# TF_VAR_* env vars -> Key Vault -> AKS pod via Workload Identity + CSI
# driver at runtime (see workload_identity.tf and
# ../deployment/secret-provider-class.yaml).
