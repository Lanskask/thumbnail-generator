# -----------------------------------------------------------------------------
# make-thumbnail: triggered by new objects landing in the source bucket
# -----------------------------------------------------------------------------

resource "google_cloudfunctions2_function" "make_thumbnail" {
  name     = "${var.name_prefix}-make-thumbnail"
  location = var.region
  project  = var.project_id

  build_config {
    runtime     = "python312"
    entry_point = "make_thumbnail"
    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.make_thumbnail_zip.name
      }
    }
  }

  service_config {
    max_instance_count    = 3
    available_memory      = "256Mi"
    timeout_seconds       = 60
    service_account_email = google_service_account.make_thumbnail.email
    environment_variables = {
      DEST_BUCKET = google_storage_bucket.dest.name
    }
  }

  event_trigger {
    trigger_region        = var.region
    event_type            = "google.cloud.storage.object.v1.finalized"
    retry_policy          = "RETRY_POLICY_DO_NOT_RETRY"
    service_account_email = google_service_account.make_thumbnail.email

    event_filters {
      attribute = "bucket"
      value     = google_storage_bucket.source.name
    }
  }

  depends_on = [
    google_project_service.required,
    google_project_iam_member.gcs_sa_pubsub_publisher,
    google_project_iam_member.make_thumbnail_event_receiver,
    google_project_iam_member.pubsub_sa_token_creator,
  ]
}

# gen2 functions run on Cloud Run under the hood; the trigger's invoking
# identity needs run.invoker on that underlying service.
resource "google_cloud_run_service_iam_member" "make_thumbnail_invoker" {
  location = google_cloudfunctions2_function.make_thumbnail.location
  project  = var.project_id
  service  = google_cloudfunctions2_function.make_thumbnail.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.make_thumbnail.email}"
}

# -----------------------------------------------------------------------------
# get-upload-url: HTTP function, called by the frontend
# -----------------------------------------------------------------------------

resource "google_cloudfunctions2_function" "get_upload_url" {
  name     = "${var.name_prefix}-get-upload-url"
  location = var.region
  project  = var.project_id

  build_config {
    runtime     = "python312"
    entry_point = "get_upload_url"
    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.get_upload_url_zip.name
      }
    }
  }

  service_config {
    max_instance_count    = 3
    available_memory      = "256Mi"
    timeout_seconds       = 30
    service_account_email = google_service_account.get_upload_url.email
    environment_variables = {
      SOURCE_BUCKET  = google_storage_bucket.source.name
      DEST_BUCKET    = google_storage_bucket.dest.name
      ALLOWED_ORIGIN = "*"
    }
  }

  depends_on = [google_project_service.required]
}

# Allow unauthenticated invocations (this is a public upload-URL issuer;
# it does not touch data directly, only mints short-lived signed URLs).
resource "google_cloud_run_service_iam_member" "get_upload_url_public" {
  location = google_cloudfunctions2_function.get_upload_url.location
  project  = var.project_id
  service  = google_cloudfunctions2_function.get_upload_url.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
