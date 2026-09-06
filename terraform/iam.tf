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
# We use the google_storage_project_service_account *data source* rather
# than the google_project_service_identity *resource* here: the latter has
# a known provider bug where its email/member attributes come back empty
# when the identity is created in the same apply as the API being enabled
# (https://github.com/hashicorp/terraform-provider-google/issues/18649).
# The data source instead directly calls GCS's own serviceAccount endpoint,
# which reliably returns the service agent's email on every read.
data "google_storage_project_service_account" "gcs_sa" {
  project = var.project_id

  depends_on = [google_project_service.required]
}

resource "google_project_iam_member" "gcs_sa_pubsub_publisher" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${data.google_storage_project_service_account.gcs_sa.email_address}"
}

# Eventarc's GCS trigger path additionally requires the Pub/Sub service
# agent to hold Token Creator *on itself*, so it can mint auth tokens when
# delivering events to the underlying Cloud Run trigger. Without this,
# `terraform apply` fails at trigger-creation time with:
#   "Permission denied while using the Eventarc Service Agent"
# even though eventarc.serviceAgent is already correctly bound (that role
# alone is not sufficient for GCS-sourced triggers).
# https://cloud.google.com/eventarc/docs/troubleshooting#trigger-permission-denied
#
# The Pub/Sub service agent's email follows Google's fixed, documented
# service-agent naming convention, so it's built from the project number
# directly rather than depending on a flaky google_project_service_identity
# resource (see the comment on the GCS data source above for why that
# resource is avoided elsewhere in this file).
data "google_project" "current" {
  project_id = var.project_id
}

resource "google_project_iam_member" "pubsub_sa_token_creator" {
  project = var.project_id
  role    = "roles/iam.serviceAccountTokenCreator"
  member  = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"

  depends_on = [google_project_service.required]
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
