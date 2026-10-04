.PHONY: help install test test-unit test-e2e-cloudflare lint format typecheck check \
        deploy deploy-cloudflare cf-install cf-test cf-build cf-plan verify-cloudflare destroy-cloudflare

DEPLOY_TARGET ?= cloudflare
# Public URL of the Cloudflare copy (see `terraform output url_hint`); used by verify/destroy guards.
CLOUDFLARE_URL ?=
export DEPLOY_TARGET CLOUDFLARE_URL

help:
	@echo "Setup:"
	@echo "  make install       Install all deps (Poetry)"
	@echo ""
	@echo "Tests:"
	@echo "  make test-unit     Run unit tests only (no network)"
	@echo "  make test-e2e-cloudflare  Run e2e tests against the Cloudflare Worker (needs CLOUDFLARE_URL=https://...)"
	@echo "  make test          Run unit tests"
	@echo ""
	@echo "Code quality:"
	@echo "  make lint          Ruff lint"
	@echo "  make format        Ruff format (auto-fix)"
	@echo "  make typecheck     mypy across tests/"
	@echo "  make check         lint + typecheck + test-unit"
	@echo ""
	@echo ""
	@echo "Deploy (DEPLOY_TARGET=cloudflare):"
	@echo "  make deploy                          deploy to \$$(DEPLOY_TARGET)"
	@echo "  make cf-install / cf-test / cf-build   install, test, bundle the Worker (cloudflare/, esbuild)"
	@echo "  make cf-plan                         terraform plan for the Cloudflare resources (read-only)"
	@echo "  make deploy DEPLOY_TARGET=cloudflare bundle, then terraform apply (creates the R2 bucket + Worker)"
	@echo "  make verify-cloudflare CLOUDFLARE_URL=https://...   upload API answers"

install:
	poetry install

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
test-unit:
	poetry run pytest tests/unit -v -m "not e2e"


test-e2e-cloudflare:
	@test -n "$(CLOUDFLARE_URL)" || { echo "Set CLOUDFLARE_URL=https://thumbnail-generator.physics-study-dashboards.workers.dev (or a local wrangler dev URL)"; exit 1; }
	poetry run pytest tests/e2e/test_thumbnail_cloudflare.py -v -m e2e_cloudflare

test: test-unit

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
		tests

check: lint typecheck test-unit






# ---------------------------------------------------------------------------
# Deploy targets
# ---------------------------------------------------------------------------
deploy: deploy-$(DEPLOY_TARGET)


cf-install:
	cd cloudflare && bun install

cf-test:
	cd cloudflare && bun run test && bun run typecheck

# Terraform does not bundle TypeScript, so esbuild produces cloudflare/build/index.js first.
cf-build:
	cd cloudflare && bun run build

cf-plan: cf-build
	cd cloudflare/terraform && terraform init && terraform plan

# Needs CLOUDFLARE_API_TOKEN and cloudflare/terraform/terraform.tfvars (account_id). Creates cloud resources.
deploy-cloudflare: cf-test cf-build
	cd cloudflare/terraform && terraform init && terraform apply

verify-cloudflare:
	@test -n "$(CLOUDFLARE_URL)" || { echo "Set CLOUDFLARE_URL=https://thumbnail-generator.physics-study-dashboards.workers.dev"; exit 1; }
	curl -fsS -X POST -H 'content-type: application/json' -d '{"filename":"a.png","contentType":"image/png"}' "$(CLOUDFLARE_URL)/api?action=upload"; echo


# Delete the Cloudflare Worker + R2 bucket (Terraform). Dry run unless APPLY=1.
destroy-cloudflare:
	@scripts/guard-destroy.sh cloudflare thumbnail-generator "cd cloudflare/terraform && terraform destroy"
