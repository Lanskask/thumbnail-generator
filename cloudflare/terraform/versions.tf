terraform {
  required_version = ">= 1.5"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.0"
    }
  }
}

# Auth: export CLOUDFLARE_API_TOKEN (a scoped API token, not the Global API key).
# Needed permissions: Account > Workers Scripts > Edit, Account > Workers R2 Storage > Edit.
provider "cloudflare" {}
