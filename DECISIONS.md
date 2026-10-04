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
