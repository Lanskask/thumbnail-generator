# -----------------------------------------------------------------------------
# Service accounts (least privilege: separate identity per function)
# -----------------------------------------------------------------------------

resource "google_service_account" "make_thumbnail" {
  account_id   = "${var.name_prefix}-make-thumb"
  display_name = "make-thumbnail Cloud Function identity"
  project      = var.project_id
}

resource "google_service_account" "get_upload_url" {
  account_id   = "${var.name_prefix}-upload-url"
  display_name = "get-upload-url Cloud Function identity"
  project      = var.project_id
}

# make-thumbnail: read from source bucket, write to dest bucket.
resource "google_storage_bucket_iam_member" "make_thumbnail_reads_source" {
  bucket = google_storage_bucket.source.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.make_thumbnail.email}"
}

resource "google_storage_bucket_iam_member" "make_thumbnail_writes_dest" {
  bucket = google_storage_bucket.dest.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.make_thumbnail.email}"
}

# get-upload-url: needs objectAdmin on source (to sign PUT URLs) and
# objectViewer on dest (to check existence / sign GET URLs), plus permission
# to sign as itself (V4 signing requires the token creator role on its own
# service account when running on Cloud Functions/Cloud Run's default ADC).
resource "google_storage_bucket_iam_member" "upload_url_writes_source" {
  bucket = google_storage_bucket.source.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.get_upload_url.email}"
}

resource "google_storage_bucket_iam_member" "upload_url_reads_dest" {
  bucket = google_storage_bucket.dest.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.get_upload_url.email}"
}

resource "google_service_account_iam_member" "upload_url_self_sign" {
  service_account_id = google_service_account.get_upload_url.name
  role                = "roles/iam.serviceAccountTokenCreator"
  member              = "serviceAccount:${google_service_account.get_upload_url.email}"
}

# Eventarc (which the GCS trigger relies on under the hood) needs the
# pubsub publisher role on the storage service agent.
#
# depends_on is required here: without it, Terraform can call
# generateServiceIdentity for storage.googleapis.com before the API is
# confirmed enabled on the project, which returns an empty ServiceIdentity
# (email/member null) even though the resource "succeeds". See
# https://github.com/hashicorp/terraform-provider-google/issues/18649.
resource "google_project_service_identity" "gcs_sa" {
  provider = google-beta
  project  = var.project_id
  service  = "storage.googleapis.com"

  depends_on = [google_project_service.required]
}

resource "google_project_iam_member" "gcs_sa_pubsub_publisher" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = google_project_service_identity.gcs_sa.member
}

# The event trigger's service account needs eventarc.eventReceiver at the
# project level, and run.invoker on the underlying Cloud Run service that
# gen2 functions are built on (granted after the function exists, see
# functions.tf).
resource "google_project_iam_member" "make_thumbnail_event_receiver" {
  project = var.project_id
  role    = "roles/eventarc.eventReceiver"
  member  = "serviceAccount:${google_service_account.make_thumbnail.email}"
}
