output "frontend_url" {
  description = "Public URL of the upload webpage."
  value       = "https://storage.googleapis.com/${google_storage_bucket.frontend.name}/index.html"
}

output "get_upload_url_function_url" {
  description = "Endpoint of the signed-URL issuing function (baked into the frontend automatically)."
  value       = google_cloudfunctions2_function.get_upload_url.url
}

output "source_bucket" {
  description = "Bucket that receives raw uploads."
  value       = google_storage_bucket.source.name
}

output "dest_bucket" {
  description = "Bucket that receives generated thumbnails."
  value       = google_storage_bucket.dest.name
}
