# Decisions

## Cloudflare target: one Worker, one R2 bucket, Images binding (2026-10-03)
- **Requirement:** add Cloudflare free tier as an extra deploy target; keep GCP working.
- **Choice:** Workers cannot run Pillow (native Python extension). The Images binding does the resize
  (`width=200,height=200,fit=scale-down`, same result as PIL `thumbnail`), so no image library is shipped.
- **API shape kept** (`POST ?action=upload`, `GET ?action=download`) so the frontend is unchanged. Difference:
  the browser PUTs bytes to the Worker (`/api/put/<name>`) instead of a signed bucket URL, and the thumbnail is
  made in that request. That removes the event trigger, the signing logic and the secrets, and the source image
  is not stored (GCP kept it 7 days), so only one R2 bucket exists.
- **Limits** (read from the official pages on 2026-10-03): Images Free 5,000 unique transformations/month;
  binding input up to 20 MB (the Worker caps at 10 MB); Workers Free 100,000 requests/day, 10 ms CPU.
- **Not verified:** the Worker has only been run against mocks (8 vitest tests) and `wrangler deploy --dry-run`.
  The real Images binding and R2 have not been called yet, because that needs a login and creates a bucket.
- **Delete from GCP:** `make destroy-gcp` via `scripts/guard-destroy.sh` (dry run default, Cloudflare URL must answer,
  `APPLY=1`, type the project ID).

## Cloudflare resources managed with Terraform, not wrangler (2026-10-04)
- **Requirement:** you prefer Terraform over the JS tooling (wrangler config); the GCP side already uses Terraform.
- **Choice:** `cloudflare/terraform/` uses provider `cloudflare/cloudflare ~> 5.0` (resources `cloudflare_r2_bucket`,
  `cloudflare_worker`, `cloudflare_worker_version`, `cloudflare_workers_deployment`; bindings `r2_bucket` and `images`
  exist in the provider schema). `wrangler.jsonc` and the wrangler dependency are removed.
- **Bundling:** Terraform uploads files as they are and does not compile TypeScript (Cloudflare's own IaC page says to
  bundle first), so esbuild produces `build/index.js` (`make cf-build`).
- **Frontend:** Workers Static Assets needs an upload session and a token (`assets.jwt`), which is not a plain Terraform
  step, so the 4 KB page is generated into `src/frontend.generated.ts` and served by the Worker itself.
- **Verified:** `terraform validate` passes, 9 vitest tests pass, tsc clean, esbuild bundle is 8.7 KB.
  **Not verified:** `terraform plan/apply` (needs your API token and account ID), and everything from the earlier note
  about the real Images binding/R2 behaviour.
- **Terraform state** is local (`terraform.tfstate`, gitignored), like the GCP one. Keep it until `destroy` finishes.

## Cloudflare e2e test, R2 expiry, and two bugs it found (2026-10-04)
- **Requirement:** an e2e test for the Cloudflare side, and the same 7-day expiry the GCP buckets had.
- **Expiry:** `cloudflare_r2_bucket_lifecycle` deletes objects `thumbnail_ttl_days` (default 7) after upload. Both GCP buckets
  (source and dest) used `age = 7`; the Cloudflare version has one bucket (no source copy is stored).
- **E2E:** `tests/e2e/test_thumbnail_cloudflare.py` with marker `e2e_cloudflare` (kept apart from the GCP `e2e` marker),
  helpers in `tests/common/cloudflare_client.py`. It skips unless `CLOUDFLARE_URL` is set.
- **Measured (local `wrangler dev`, local R2 + local Images simulation, not Cloudflare's real services):** 11 passed.
  Running it first failed and exposed two bugs that mocked unit tests could not see:
  1. The bundle exported helper functions next to the default handler; the Workers runtime refuses any named export that
     is not a handler ("Incorrect type for map entry 'MAX_UPLOAD_BYTES'"). The same bundle would have failed on the real
     deploy. Fix: `src/worker.ts` exports only the default handler and is the esbuild entry.
  2. R2 `put` rejected the Images response body ("readable stream must have a known length"). Fix: read it with
     `arrayBuffer()` first. A unit-test mock now rejects streams.
- **Still unverified:** the real Images binding and real R2 (the local run simulates both); the first deploy is the proof.

## GCP stack removed; README rewritten for Cloudflare only (2026-10-04)
- **Requirement:** Cloudflare is the only target now; the GCP project was destroyed (`terraform state list` was empty before `terraform/` was deleted).
- **Removed:** `terraform/`, `functions/`, `main.py`, `requirements.txt`, the GCP e2e/unit tests and the google/flask/cloudevents dependencies. Python stays only for the Cloudflare e2e tests.
- **Measured after removal:** `make check` (ruff, mypy, 10 unit tests) passes; `make test-e2e-cloudflare` 11 passed against the live Worker.
