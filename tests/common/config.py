"""
Test configuration: resolves the deployed `get-upload-url` function endpoint
from either an explicit env var or `terraform output`, so the e2e suite
always targets whatever is actually deployed instead of a hardcoded URL.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

TERRAFORM_DIR: Path = Path(__file__).resolve().parents[2] / "terraform"

ENV_FUNCTION_URL: str = "THUMBNAILER_FUNCTION_URL"
ENV_SOURCE_BUCKET: str = "THUMBNAILER_SOURCE_BUCKET"
ENV_DEST_BUCKET: str = "THUMBNAILER_DEST_BUCKET"


class ConfigError(RuntimeError):
    """Raised when the deployed endpoint/buckets cannot be resolved."""


@dataclass(frozen=True)
class DeploymentConfig:
    """Everything the e2e suite needs to talk to a live deployment."""

    function_url: str
    source_bucket: str
    dest_bucket: str


def _terraform_output(key: str) -> str | None:
    try:
        result = subprocess.run(
            ["terraform", "output", "-raw", key],
            cwd=TERRAFORM_DIR,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if result.returncode != 0:
        return None

    value = result.stdout.strip()
    return value or None


def load_deployment_config() -> DeploymentConfig:
    """Resolve the live function URL + bucket names.

    Resolution order per value: explicit env var, then `terraform output`
    against terraform/ (requires a prior `terraform apply` and local state).
    Raises ConfigError with an actionable message if nothing resolves.
    """
    function_url = os.environ.get(ENV_FUNCTION_URL) or _terraform_output(
        "get_upload_url_function_url"
    )
    source_bucket = os.environ.get(ENV_SOURCE_BUCKET) or _terraform_output("source_bucket")
    dest_bucket = os.environ.get(ENV_DEST_BUCKET) or _terraform_output("dest_bucket")

    missing = [
        name
        for name, value in (
            (ENV_FUNCTION_URL, function_url),
            (ENV_SOURCE_BUCKET, source_bucket),
            (ENV_DEST_BUCKET, dest_bucket),
        )
        if not value
    ]
    if missing:
        raise ConfigError(
            "Could not resolve deployment config for: "
            + ", ".join(missing)
            + ". Either `terraform apply` the infra in terraform/ first (so "
            "`terraform output` resolves it), or set the env var(s) "
            "directly, e.g.:\n"
            f"  export {ENV_FUNCTION_URL}=https://...\n"
            f"  export {ENV_SOURCE_BUCKET}=thumbnailer-src-<project>\n"
            f"  export {ENV_DEST_BUCKET}=thumbnailer-out-<project>"
        )

    assert function_url and source_bucket and dest_bucket  # for type-checkers
    return DeploymentConfig(
        function_url=function_url,
        source_bucket=source_bucket,
        dest_bucket=dest_bucket,
    )
