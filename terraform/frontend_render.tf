# Renders frontend/index.html with the deployed get-upload-url function's
# endpoint baked in, so the static page needs no runtime config step.

locals {
  frontend_index_rendered = "${path.module}/.rendered/index.html"
}

resource "local_file" "frontend_index_rendered" {
  filename = local.frontend_index_rendered
  content = replace(
    file("${path.module}/../frontend/index.html"),
    "__GET_UPLOAD_URL_ENDPOINT__",
    google_cloudfunctions2_function.get_upload_url.url
  )
}
