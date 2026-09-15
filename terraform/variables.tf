variable "project" {
  description = *******************************************"
  type        = *****g
  default     = *************"
}

variable "environment" {
  description = **************************************"
  type        = *****g
  default     = ****"
}

variable "location" {
  description = *************"
  type        = *****g
  default     = *************"
}

variable "resource_group_name" {
  description = ******************************************"
  type        = *****g
  default     = ****************"
}

variable "aks_cluster_name" {
  description = ****************************************************"
  type        = *****g
  default     = *****************"
}

variable "aks_oidc_issuer_url" {
  description = ****************************************************************************************************************************************"
  type        = *****g
}

variable "k8s_namespace" {
  description = *************************************"
  type        = *****g
  default     = *******"
}

variable "k8s_service_account_name" {
  description = *****************************************************************"
  type        = *****g
  default     = ********************"
}

# ---- Secret VALUES -------------------------------------------------------
# None of these have defaults. Supply them via:
#   - a gitignored terraform.tfvars file, OR
#   - TF_VAR_xxx environment variables (preferred for CI/CD), OR
#   - a pipeline secret store (GitHub Actions secrets, Azure DevOps variable groups)
# They are marked sensitive so Terraform redacts them from CLI/plan output,
# and they are written into Key Vault, never into Kubernetes YAML or this repo.

variable "pg_admin_password" {
  description = **************************"
  type        = *****g
  sensitive   = ***e
}

variable "pg_host" {
  description = ****************************************************************"
  type        = *****g
}

variable "pg_user" {
  description = **************************"
  type        = *****g
  default     = ********"
}

variable "mongo_connection_string" {
  description = ********************************************"
  type        = *****g
  sensitive   = ***e
}

variable "azure_openai_endpoint" {
  description = *******************************"
  type        = *****g
}

variable "azure_openai_api_key" {
  description = *********************"
  type        = *****g
  sensitive   = ***e
}

variable "api_key" {
  description = **********************************************************************************"
  type        = *****g
  sensitive   = ***e
}

variable "azure_language_endpoint" {
  description = ***************************************************************************"
  type        = *****g
}

variable "azure_language_key" {
  description = *******************************"
  type        = *****g
  sensitive   = ***e
}

variable "whatsapp_verify_token" {
  description = **************************************************************************************************************************"
  type        = *****g
  sensitive   = ***e
}

variable "whatsapp_access_token" {
  description = *********************************************************************"
  type        = *****g
  sensitive   = ***e
}

variable "whatsapp_phone_number_id" {
  description = *******************************************************************"
  type        = *****g
}

variable "whatsapp_app_secret" {
  description = ******************************************************************************"
  type        = *****g
  sensitive   = ***e
}

variable "jwt_secret" {
  description = ***************************************************"
  type        = *****g
  sensitive   = ***e
}

variable "export_hash_secret" {
  description = **********************************************************************************************************************"
  type        = *****g
  sensitive   = ***e
}

variable "client_credentials_json" {
  description = *********************************************************************************"
  type        = *****g
  sensitive   = ***e
}

variable "smtp_host" {
  description = ***************************************************************************************"
  type        = *****g
  default     = *"
}

variable "smtp_user" {
  description = **************"
  type        = *****g
  default     = *"
}

variable "smtp_password" {
  description = **************"
  type        = *****g
  sensitive   = ***e
  default     = *"
}

variable "alert_from_email" {
  description = ****************************************"
  type        = *****g
  default     = *"
}

variable "alert_to_emails" {
  description = ***************************************************************"
  type        = *****g
  default     = *"
}
