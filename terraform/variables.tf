variable "project" {
  description = "Short project name used in resource naming"
  type        = string
  default     = "edtech-india"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "location" {
  description = "Azure region"
  type        = string
  default     = "centralindia"
}

variable "resource_group_name" {
  description = "Resource group that holds Key Vault + AKS"
  type        = string
  default     = "rg-edtech-india"
}

variable "aks_cluster_name" {
  description = "Name of the existing (or to-be-created) AKS cluster"
  type        = string
  default     = "aks-edtech-india"
}

variable "aks_oidc_issuer_url" {
  description = "OIDC issuer URL of the AKS cluster (from `az aks show --query oidcIssuerProfile.issuerUrl`). Required for Workload Identity federation."
  type        = string
}

variable "k8s_namespace" {
  description = "Kubernetes namespace the app runs in"
  type        = string
  default     = "edtech"
}

variable "k8s_service_account_name" {
  description = "Kubernetes ServiceAccount that will assume the Workload Identity"
  type        = string
  default     = "edtech-india-api-sa"
}

# ---- Secret VALUES -------------------------------------------------------
# None of these have defaults. Supply them via:
#   - a gitignored terraform.tfvars file, OR
#   - TF_VAR_xxx environment variables (preferred for CI/CD), OR
#   - a pipeline secret store (GitHub Actions secrets, Azure DevOps variable groups)
# They are marked sensitive so Terraform redacts them from CLI/plan output,
# and they are written into Key Vault, never into Kubernetes YAML or this repo.

variable "pg_admin_password" {
  description = "PostgreSQL admin password"
  type        = string
  sensitive   = true
}

variable "pg_host" {
  description = "PostgreSQL FQDN (Azure Database for PostgreSQL Flexible Server)"
  type        = string
}

variable "pg_user" {
  description = "PostgreSQL admin username"
  type        = string
  default     = "pgadmin"
}

variable "mongo_connection_string" {
  description = "Cosmos DB for MongoDB API connection string"
  type        = string
  sensitive   = true
}

variable "azure_openai_endpoint" {
  description = "Azure OpenAI resource endpoint"
  type        = string
}

variable "azure_openai_api_key" {
  description = "Azure OpenAI API key"
  type        = string
  sensitive   = true
}

variable "api_key" {
  description = "Shared API key the Sanic app checks on the x-api-key header for non-health routes"
  type        = string
  sensitive   = true
}

variable "azure_language_endpoint" {
  description = "Azure AI Language resource endpoint (used for question language detection)"
  type        = string
}

variable "azure_language_key" {
  description = "Azure AI Language resource key"
  type        = string
  sensitive   = true
}

variable "whatsapp_verify_token" {
  description = "Arbitrary string set in the Meta App dashboard webhook config; must match what the /webhook/whatsapp GET handshake checks"
  type        = string
  sensitive   = true
}

variable "whatsapp_access_token" {
  description = "Meta WhatsApp Cloud API access token (system user token, long-lived)"
  type        = string
  sensitive   = true
}

variable "whatsapp_phone_number_id" {
  description = "Meta WhatsApp Cloud API phone number ID the bot sends replies from"
  type        = string
}

variable "whatsapp_app_secret" {
  description = "Meta App secret, used to verify X-Hub-Signature-256 on incoming webhook calls"
  type        = string
  sensitive   = true
}

variable "jwt_secret" {
  description = "Secret used to sign/verify per-client JWTs (HS256)"
  type        = string
  sensitive   = true
}

variable "client_credentials_json" {
  description = "JSON map of client_id -> {secret, state} for JWT-based, state-scoped API clients"
  type        = string
  sensitive   = true
}

variable "smtp_host" {
  description = "SMTP host for high-risk alert emails (e.g. an Azure Communication Services SMTP relay)"
  type        = string
  default     = ""
}

variable "smtp_user" {
  description = "SMTP username"
  type        = string
  default     = ""
}

variable "smtp_password" {
  description = "SMTP password"
  type        = string
  sensitive   = true
  default     = ""
}

variable "alert_from_email" {
  description = "From address for high-risk alert emails"
  type        = string
  default     = ""
}

variable "alert_to_emails" {
  description = "Comma-separated recipient addresses for high-risk alert emails"
  type        = string
  default     = ""
}
