# -----------------------------------------------------------------------------
# Buckets
# -----------------------------------------------------------------------------
# Names must be globally unique across all of GCS, so we suffix with the
# project ID (which is itself globally unique).

resource "google_storage_bucket" "source" {
  name                        = "${var.name_prefix}-src-${var.project_id}"
  location                    = var.region
  project                     = var.project_id
  force_destroy               = true
  uniform_bucket_level_access = true

  # Keep the bucket tidy / cheap: expire raw uploads after 7 days.
  lifecycle_rule {
    condition {
      age = 7
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_storage_bucket" "dest" {
  name                        = "${var.name_prefix}-out-${var.project_id}"
  location                    = var.region
  project                     = var.project_id
  force_destroy               = true
  uniform_bucket_level_access = true

  lifecycle_rule {
    condition {
      age = 7
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.required]
}

# Static frontend hosting bucket. Publicly readable (it's just the HTML/JS/CSS),
# served via GCS's website endpoint.
resource "google_storage_bucket" "frontend" {
  name                        = "${var.name_prefix}-web-${var.project_id}"
  location                    = var.region
  project                     = var.project_id
  force_destroy               = true
  uniform_bucket_level_access = true

  website {
    main_page_suffix = "index.html"
    not_found_page   = "index.html"
  }

  depends_on = [google_project_service.required]
}

resource "google_storage_bucket_iam_member" "frontend_public_read" {
  bucket = google_storage_bucket.frontend.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

resource "google_storage_bucket_object" "frontend_index" {
  name         = "index.html"
  bucket       = google_storage_bucket.frontend.name
  source       = local.frontend_index_rendered
  content_type = "text/html"

  depends_on = [local_file.frontend_index_rendered]
}
