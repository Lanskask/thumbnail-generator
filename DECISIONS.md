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
