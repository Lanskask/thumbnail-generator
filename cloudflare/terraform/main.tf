# Cloudflare equivalent of ../../terraform (GCP): one R2 bucket + one Worker.
# The Worker code is bundled first (`make cf-build` -> ../build/index.js); Terraform does not bundle.

resource "cloudflare_r2_bucket" "thumbs" {
  account_id = var.account_id
  name       = var.bucket_name
}

# Same housekeeping as the GCP buckets (lifecycle_rule age = 7): expire thumbnails after a week.
resource "cloudflare_r2_bucket_lifecycle" "thumbs" {
  account_id  = var.account_id
  bucket_name = cloudflare_r2_bucket.thumbs.name

  rules = [{
    id         = "expire-thumbnails"
    enabled    = true
    conditions = { prefix = "" }
    delete_objects_transition = {
      condition = {
        type    = "Age"
        max_age = var.thumbnail_ttl_days * 24 * 60 * 60 # seconds
      }
    }
  }]
}

resource "cloudflare_worker" "api" {
  account_id = var.account_id
  name       = var.worker_name

  subdomain = {
    enabled = true # serve on <name>.<account-subdomain>.workers.dev
  }
  observability = {
    enabled = true
  }
}

resource "cloudflare_worker_version" "api" {
  account_id         = var.account_id
  worker_id          = cloudflare_worker.api.id
  compatibility_date = var.compatibility_date
  main_module        = "index.js"

  modules = [{
    name         = "index.js"
    content_type = "application/javascript+module"
    content_file = "${path.module}/../build/index.js" # a new version is created whenever this file changes
  }]

  bindings = [
    {
      type        = "r2_bucket"
      name        = "THUMBS"
      bucket_name = cloudflare_r2_bucket.thumbs.name
    },
    {
      type = "images"
      name = "IMAGES"
    },
  ]
}

resource "cloudflare_workers_deployment" "api" {
  account_id  = var.account_id
  script_name = cloudflare_worker.api.name
  strategy    = "percentage"
  versions = [{
    percentage = 100
    version_id = cloudflare_worker_version.api.id
  }]
}
