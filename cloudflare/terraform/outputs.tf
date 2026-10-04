output "worker_name" {
  value = cloudflare_worker.api.name
}

output "bucket_name" {
  value = cloudflare_r2_bucket.thumbs.name
}

output "url_hint" {
  value       = "https://${cloudflare_worker.api.name}.<your-account-subdomain>.workers.dev"
  description = "Your account subdomain is shown in the dashboard under Workers & Pages."
}
