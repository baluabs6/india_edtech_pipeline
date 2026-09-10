terraform {
  required_version = *********"

  required_providers {
    azurerm = {
      source  = ******************"
      version = *********"
    }
    azuread = {
      source  = ******************"
      version = ********"
    }
  }

  # Remote state — never commit local .tfstate, it can contain secret metadata.
  # Configure via `terraform init -backend-config=backend.hcl` (see backend.hcl.example).
  backend "azurerm" {}
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy    = ****e
      recover_soft_deleted_key_vaults = ***e
    }
  }
}

provider "azuread" {}

data "azurerm_client_config" "current" {}
