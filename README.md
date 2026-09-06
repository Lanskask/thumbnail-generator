# Thumbnail Generator — Web Upload + Cloud Function (GCP Always Free tier)

A small full-stack serverless project, deployed entirely with Terraform:

- A **static upload webpage** (drag-and-drop an image)
- A **Cloud Function** that issues short-lived signed URLs so the browser can
  upload directly to Cloud Storage and poll for the result
- A **Cloud Function** triggered by new uploads that generates a 200x200
  thumbnail
- All infrastructure defined as code, no manual clicking in the console

## Architecture

```
                 ┌─────────────────────────────┐
   Browser  ---> │  GCS static website bucket   │  (index.html, public read)
                 └─────────────────────────────┘
                              │
                 (1) POST ?action=upload
                              v
                 ┌─────────────────────────────┐
                 │ Cloud Function: get-upload-  │  HTTP, unauthenticated
                 │ url  (mints V4 signed URLs)  │
                 └─────────────────────────────┘
                              │
                 (2) returns a signed PUT URL
                              v
   Browser  --- PUT image bytes directly ---> gs://<src bucket>
                              │
                 (3) GCS "finalize" event (Eventarc)
                              v
                 ┌─────────────────────────────┐
                 │ Cloud Function:              │  event-triggered
                 │ make-thumbnail (Pillow)      │
                 └─────────────────────────────┘
                              │
                 (4) writes thumb_<name>
                              v
                        gs://<dest bucket>
                              │
                 (5) Browser polls get-upload-url ?action=download
                     until the signed GET URL resolves
                              v
                       Thumbnail displayed
```

No file bytes ever pass through a server you pay per-request/per-CPU-second
for beyond the two lightweight function invocations — the actual upload and
download happen directly between the browser and Cloud Storage via signed
URLs.

## Why this stays in the Always Free tier

| Resource | Always Free allowance | This project's usage |
|---|---|---|
| Cloud Functions (2nd gen, backed by Cloud Run) | 2M invocations/mo, 400,000 GB-seconds, 200,000 GHz-seconds compute | 2 invocations per upload (get URL + generate thumbnail) |
| Cloud Storage | 5 GB-months (US regions), 5,000 Class A + 50,000 Class B ops/mo | 3 small buckets; uploads auto-expire after 7 days |
| Network egress | 5 GB/month (excl. China/Australia) | Only when viewing thumbnails/frontend |
| Eventarc / Pub/Sub | 10 GB/mo message delivery free | One event per upload |

Realistic personal/demo use (dozens to low hundreds of uploads) will not
incur any charge. Heavy traffic (many thousands of large images) could.
Set a budget alert (see below) to be sure.

## Prerequisites

1. **MFA enabled** on your Google account — required for any Cloud Console/API
   access since May 2025: <https://myaccount.google.com/signinoptions/two-step-verification>
2. **A GCP project with a billing account linked** (required to enable APIs,
   even for free-tier-only usage):
   ```
   gcloud projects create YOUR_PROJECT_ID --name="Thumbnail Demo"
   gcloud billing projects link YOUR_PROJECT_ID --billing-account=YOUR_BILLING_ACCOUNT_ID
   ```
3. **Terraform** >= 1.5: <https://developer.hashicorp.com/terraform/install>
4. **gcloud CLI**, authenticated with Application Default Credentials:
   ```
   gcloud auth login
   gcloud auth application-default login
   ```

## Deploy

```
cd terraform
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars with your project ID

terraform init
terraform plan
terraform apply
```

Terraform will:
- Enable all required APIs
- Create 4 buckets: source uploads, thumbnail output, function source, and
  the public frontend
- Deploy both Cloud Functions with least-privilege service accounts
- Render `frontend/index.html` with the deployed function URL baked in and
  upload it to the public bucket

When it finishes, `terraform output frontend_url` gives you the page to open.

## Test

Open the `frontend_url` output in a browser, drop in an image, and watch it
resize.

Or from the CLI:
```
curl -X POST "$(terraform output -raw get_upload_url_function_url)?action=upload" \
  -H "Content-Type: application/json" \
  -d '{"filename":"test.jpg","contentType":"image/jpeg"}'
# then PUT the file to the returned uploadUrl, and poll ?action=download
```

## Type checking

Both Cloud Function sources are fully typed (`from __future__ import
annotations`, typed signatures throughout) and pass `mypy --ignore-missing-imports`
cleanly. If you modify them:
```
pip install mypy functions-framework google-cloud-storage Pillow flask cloudevents
mypy --ignore-missing-imports functions/make_thumbnail/main.py
mypy --ignore-missing-imports functions/get_upload_url/main.py
```

## Files

```
terraform/           All infrastructure as code
  versions.tf           Provider requirements
  variables.tf          project_id, region, name_prefix
  apis.tf                Enables required GCP APIs
  storage.tf             3 buckets: source, dest, frontend
  functions_source.tf    Zips + uploads function source
  iam.tf                 Service accounts + least-privilege bindings
  functions.tf            Both Cloud Functions (gen2)
  frontend_render.tf     Bakes the function URL into index.html at apply time
  outputs.tf             frontend_url, function URLs, bucket names
  terraform.tfvars.example

functions/
  make_thumbnail/       Event-triggered: resizes uploaded images
  get_upload_url/       HTTP: issues signed upload/download URLs

frontend/
  index.html            Upload UI (vanilla HTML/CSS/JS, no build step)
```

## Tear down

```
cd terraform
terraform destroy
```

This deletes every resource Terraform created — functions, buckets (and
their contents, via `force_destroy`), and service accounts.

## Monitoring usage / staying free

- Billing reports: <https://console.cloud.google.com/billing/reports>
- Set a budget alert (e.g. at $1) so you get an email before anything is
  ever actually charged: <https://console.cloud.google.com/billing/budgets>

## Security notes

- The `get-upload-url` function allows unauthenticated invocation because it
  only *mints signed URLs* — it never touches file bytes itself, and each
  signed URL expires in 10 minutes and is scoped to one object.
- `ALLOWED_ORIGIN` is set to `*` for CORS because GCS static website buckets
  don't have a fixed custom-domain origin out of the box. If you later put
  this behind Cloud CDN / a custom domain, tighten `ALLOWED_ORIGIN` in
  `terraform/functions.tf` to that exact origin.
- Uploaded files are restricted by content-type (PNG/JPEG/GIF/WebP only) and
  filenames are sanitized before use as object names.
- Raw uploads auto-delete after 7 days via a lifecycle rule, keeping storage
  usage (and therefore cost risk) bounded automatically.
