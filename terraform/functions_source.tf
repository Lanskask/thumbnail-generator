# Zip up each function's source directory and upload it to a dedicated
# bucket that Cloud Build/Cloud Functions reads from during deploy.

resource "google_storage_bucket" "function_source" {
  name                        = "${var.name_prefix}-fn-src-${var.project_id}"
  location                    = var.region
  project                     = var.project_id
  force_destroy               = true
  uniform_bucket_level_access = true

  depends_on = [google_project_service.required]
}

data "archive_file" "make_thumbnail_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../functions/make_thumbnail"
  output_path = "${path.module}/.build/make_thumbnail.zip"
}

resource "google_storage_bucket_object" "make_thumbnail_zip" {
  name   = "make_thumbnail-${data.archive_file.make_thumbnail_zip.output_md5}.zip"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.make_thumbnail_zip.output_path
}

data "archive_file" "get_upload_url_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../functions/get_upload_url"
  output_path = "${path.module}/.build/get_upload_url.zip"
}

resource "google_storage_bucket_object" "get_upload_url_zip" {
  name   = "get_upload_url-${data.archive_file.get_upload_url_zip.output_md5}.zip"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.get_upload_url_zip.output_path
}
