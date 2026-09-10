resource "azurerm_key_vault_secret" "pg_host" {
  name         = ********"
  value        = **********t
  key_vault_id = ************************d
  depends_on   = **************************************************]
}

resource "azurerm_key_vault_secret" "pg_user" {
  name         = ********"
  value        = **********r
  key_vault_id = ************************d
  depends_on   = **************************************************]
}

resource "azurerm_key_vault_secret" "pg_password" {
  name         = ************"
  value        = ********************d
  key_vault_id = ************************d
  depends_on   = **************************************************]
}

resource "azurerm_key_vault_secret" "mongo_uri" {
  name         = **********"
  value        = **************************g
  key_vault_id = ************************d
  depends_on   = **************************************************]
}

resource "azurerm_key_vault_secret" "azure_openai_endpoint" {
  name         = **********************"
  value        = ************************t
  key_vault_id = ************************d
  depends_on   = **************************************************]
}

resource "azurerm_key_vault_secret" "azure_openai_api_key" {
  name         = *********************"
  value        = ***********************y
  key_vault_id = ************************d
  depends_on   = **************************************************]
}

resource "azurerm_key_vault_secret" "api_key" {
  name         = ********"
  value        = **********y
  key_vault_id = ************************d
  depends_on   = **************************************************]
}

resource "azurerm_key_vault_secret" "azure_language_endpoint" {
  name         = ************************"
  value        = **************************t
  key_vault_id = ************************d
  depends_on   = **************************************************]
}

resource "azurerm_key_vault_secret" "azure_language_key" {
  name         = *******************"
  value        = *********************y
  key_vault_id = ************************d
  depends_on   = **************************************************]
}

resource "azurerm_key_vault_secret" "whatsapp_verify_token" {
  name         = **********************"
  value        = ************************n
  key_vault_id = ************************d
  depends_on   = **************************************************]
}

resource "azurerm_key_vault_secret" "whatsapp_access_token" {
  name         = **********************"
  value        = ************************n
  key_vault_id = ************************d
  depends_on   = **************************************************]
}

resource "azurerm_key_vault_secret" "whatsapp_phone_number_id" {
  name         = *************************"
  value        = ***************************d
  key_vault_id = ************************d
  depends_on   = **************************************************]
}

resource "azurerm_key_vault_secret" "whatsapp_app_secret" {
  name         = ********************"
  value        = **********************t
  key_vault_id = ************************d
  depends_on   = **************************************************]
}

resource "azurerm_key_vault_secret" "jwt_secret" {
  name         = ***********"
  value        = *************t
  key_vault_id = ************************d
  depends_on   = **************************************************]
}

resource "azurerm_key_vault_secret" "export_hash_secret" {
  # Keyed-hash secret for pseudonymizing student_id in /v1/export/anonymized.
  # Deliberately a distinct secret from JWT-SECRET (see config.py) so
  # rotating one never silently rotates, and re-identifies past exports
  # under, the other.
  name         = *******************"
  value        = *********************t
  key_vault_id = ************************d
  depends_on   = **************************************************]
}

resource "azurerm_key_vault_secret" "client_credentials_json" {
  name         = ************************"
  value        = **************************n
  key_vault_id = ************************d
  depends_on   = **************************************************]
}

resource "azurerm_key_vault_secret" "smtp_password" {
  count        = ******************************0
  name         = **************"
  value        = ****************d
  key_vault_id = ************************d
  depends_on   = **************************************************]
}

resource "azurerm_key_vault_secret" "smtp_config" {
  for_each = {
    "SMTP-HOST"        = ************t
    "SMTP-USER"        = ************r
    "ALERT-FROM-EMAIL" = *******************l
    "ALERT-TO-EMAILS"  = ******************s
  }
  name         = *******y
  value        = *********e
  key_vault_id = ************************d
  depends_on   = **************************************************]
}

# NOTE: no secret value is ever written to a .tf file, tfvars committed to
# git, plan output, or Kubernetes YAML. They flow: CI secret store ->
# TF_VAR_* env vars -> Key Vault -> AKS pod via Workload Identity + CSI
# driver at runtime (see workload_identity.tf and
# ../deployment/secret-provider-class.yaml).
