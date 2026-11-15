variable "account_id" {
  type        = string
  description = "Cloudflare account ID (dashboard > any zone/Workers page, or `wrangler whoami`)."
}

variable "worker_name" {
  type        = string
  description = "Worker name; becomes <name>.<your-subdomain>.workers.dev."
  default     = "thumbnail-generator"
}

variable "bucket_name" {
  type        = string
  description = "R2 bucket holding the thumbnails."
  default     = "thumbnail-generator-thumbs"
}

variable "compatibility_date" {
  type        = string
  description = "Workers runtime compatibility date (was in wrangler.jsonc)."
  default     = "2026-10-01"
}

variable "thumbnail_ttl_days" {
  type        = number
  description = "Thumbnails are deleted this many days after upload (the GCP buckets used 7)."
  default     = 7
}
