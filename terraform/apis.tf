# Enable all APIs this project needs. Free to enable; only usage is billed.

locals {
  required_apis = [
    "cloudfunctions.googleapis.com",
    "cloudbuild.googleapis.com",
    "storage.googleapis.com",
    "eventarc.googleapis.com",
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "iam.googleapis.com",
  ]
}

resource "google_project_service" "required" {
  for_each = toset(local.required_apis)

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}
