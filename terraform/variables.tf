variable "project_id" {
  description = "GCP project ID to deploy into. Must already exist with a billing account linked."
  type        = string
}

variable "region" {
  description = "Region for all resources. us-central1 is Always-Free-tier eligible."
  type        = string
  default     = "us-central1"
}

variable "name_prefix" {
  description = "Prefix used for bucket names and function names, to keep resources identifiable and globally-unique (bucket names are global in GCS)."
  type        = string
  default     = "thumbnailer"
}
