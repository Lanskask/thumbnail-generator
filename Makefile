.PHONY: help install test test-unit test-e2e lint format typecheck check \
        tf-init tf-plan tf-apply tf-destroy tf-output \
        deploy deploy-gcp deploy-cloudflare cf-install cf-test cf-render-frontend cf-setup verify-cloudflare destroy-gcp

# Where `make deploy` ships to: gcp (default, Terraform) or cloudflare (Worker + R2 + Images binding).
DEPLOY_TARGET ?= gcp
# Public URL of the Cloudflare copy (printed by `wrangler deploy`); used by verify/destroy guards.
CLOUDFLARE_URL ?=
export DEPLOY_TARGET CLOUDFLARE_URL

help:
	@echo "Setup:"
	@echo "  make install       Install all deps (Poetry)"
	@echo ""
	@echo "Tests:"
	@echo "  make test-unit     Run unit tests only (no network, no GCP)"
	@echo "  make test-e2e      Run e2e tests against the LIVE deployed project"
	@echo "  make test          Run unit + e2e tests"
	@echo ""
	@echo "Code quality:"
	@echo "  make lint          Ruff lint"
	@echo "  make format        Ruff format (auto-fix)"
	@echo "  make typecheck     mypy across functions/ and tests/"
	@echo "  make check         lint + typecheck + test-unit"
	@echo ""
	@echo "Terraform (thin wrappers; you still review the plan yourself):"
	@echo "  make tf-init       terraform init"
	@echo "  make tf-plan       terraform plan"
	@echo "  make tf-apply      terraform apply"
	@echo "  make tf-destroy    terraform destroy"
	@echo "  make tf-output     terraform output"
	@echo ""
	@echo "Deploy (DEPLOY_TARGET=gcp|cloudflare, default gcp):"
	@echo "  make deploy                          deploy to \$$(DEPLOY_TARGET)"
	@echo "  make cf-install / cf-test            install / unit-test the Cloudflare Worker (cloudflare/)"
	@echo "  make cf-setup                        one-time: create the R2 bucket (creates a cloud resource)"
	@echo "  make deploy DEPLOY_TARGET=cloudflare render frontend and wrangler deploy"
	@echo "  make verify-cloudflare CLOUDFLARE_URL=https://...   upload API answers"
	@echo "  make destroy-gcp CLOUDFLARE_URL=...  DRY RUN of terraform destroy; add APPLY=1 to really delete"

install:
	poetry install

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
test-unit:
	poetry run pytest tests/unit -v -m "not e2e"

test-e2e:
	poetry run pytest tests/e2e -v -m e2e

test: test-unit test-e2e

# ---------------------------------------------------------------------------
# Code quality
# ---------------------------------------------------------------------------
lint:
	poetry run ruff check .

format:
	poetry run ruff format .
	poetry run ruff check --fix .

typecheck:
	poetry run mypy --ignore-missing-imports --explicit-package-bases \
		functions/make_thumbnail/main.py \
		functions/get_upload_url/main.py \
		tests

check: lint typecheck test-unit

# ---------------------------------------------------------------------------
# Terraform (run from terraform/; these are convenience wrappers only —
# always read the plan output yourself before typing "yes")
# ---------------------------------------------------------------------------
tf-init:
	cd terraform && terraform init

tf-plan:
	cd terraform && terraform plan

tf-apply:
	cd terraform && terraform apply

tf-destroy:
	cd terraform && terraform destroy

tf-output:
	cd terraform && terraform output

# ---------------------------------------------------------------------------
# Deploy targets
# ---------------------------------------------------------------------------
deploy: deploy-$(DEPLOY_TARGET)

deploy-gcp:
	cd terraform && terraform apply

cf-install:
	cd cloudflare && bun install

cf-test:
	cd cloudflare && bun run test && bun run typecheck

# The page calls the Worker on the same origin, so its endpoint is just "/api".
cf-render-frontend:
	sed 's|__GET_UPLOAD_URL_ENDPOINT__|/api|' frontend/index.html > cloudflare/public/index.html

# One-time. Creates a cloud resource (R2 bucket; free tier: 10 GB-month).
cf-setup:
	cd cloudflare && bunx wrangler r2 bucket create thumbnail-generator-thumbs

deploy-cloudflare: cf-render-frontend cf-test
	cd cloudflare && bunx wrangler deploy

verify-cloudflare:
	@test -n "$(CLOUDFLARE_URL)" || { echo "Set CLOUDFLARE_URL=https://thumbnail-generator.<subdomain>.workers.dev"; exit 1; }
	curl -fsS -X POST -H 'content-type: application/json' -d '{"filename":"a.png","contentType":"image/png"}' "$(CLOUDFLARE_URL)/api?action=upload"; echo

# Delete the GCP functions/buckets via Terraform. Dry run unless APPLY=1.
destroy-gcp:
	@scripts/guard-destroy.sh gcp thumbnail-generator-2127 "cd terraform && terraform destroy"
