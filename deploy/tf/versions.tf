# WP-DEPLOY-1 (R-DEPLOY-AUTOMATION). Seed of the R-MARKETPLACE IaC rung:
# provider-variable clean so the same structure extends to AWS/Azure/GCP.
terraform {
  required_version = ">= 1.6"
  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.45"
    }
  }
}

provider "hcloud" {
  token = var.hcloud_token
}
