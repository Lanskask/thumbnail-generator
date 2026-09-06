.PHONY: help install test test-unit test-e2e lint format typecheck check \
        tf-init tf-plan tf-apply tf-destroy tf-output

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
