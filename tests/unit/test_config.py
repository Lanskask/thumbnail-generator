"""Unit tests for tests/common/config.py — no real terraform/network calls."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from unittest.mock import patch

import pytest

from tests.common.config import (
    ENV_DEST_BUCKET,
    ENV_FUNCTION_URL,
    ENV_SOURCE_BUCKET,
    ConfigError,
    DeploymentConfig,
    load_deployment_config,
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Ensure no real env vars leak into these tests."""
    for var in (ENV_FUNCTION_URL, ENV_SOURCE_BUCKET, ENV_DEST_BUCKET):
        monkeypatch.delenv(var, raising=False)
    yield


class TestLoadDeploymentConfigFromEnv:
    def test_reads_all_three_from_env_without_calling_terraform(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(ENV_FUNCTION_URL, "https://example.com/fn")
        monkeypatch.setenv(ENV_SOURCE_BUCKET, "src-bucket")
        monkeypatch.setenv(ENV_DEST_BUCKET, "dest-bucket")

        with patch("tests.common.config._terraform_output") as mock_tf:
            config = load_deployment_config()
            mock_tf.assert_not_called()

        assert config == DeploymentConfig(
            function_url="https://example.com/fn",
            source_bucket="src-bucket",
            dest_bucket="dest-bucket",
        )

    def test_env_takes_precedence_over_terraform_output(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(ENV_FUNCTION_URL, "https://from-env/fn")

        with patch(
            "tests.common.config._terraform_output",
            side_effect=lambda key: {
                "get_upload_url_function_url": "https://from-terraform/fn",
                "source_bucket": "tf-src",
                "dest_bucket": "tf-dest",
            }[key],
        ):
            config = load_deployment_config()

        assert config.function_url == "https://from-env/fn"
        assert config.source_bucket == "tf-src"
        assert config.dest_bucket == "tf-dest"


class TestLoadDeploymentConfigFromTerraform:
    def test_falls_back_to_terraform_output_for_all_values(self) -> None:
        with patch(
            "tests.common.config._terraform_output",
            side_effect=lambda key: {
                "get_upload_url_function_url": "https://tf/fn",
                "source_bucket": "tf-src",
                "dest_bucket": "tf-dest",
            }[key],
        ):
            config = load_deployment_config()

        assert config == DeploymentConfig(
            function_url="https://tf/fn",
            source_bucket="tf-src",
            dest_bucket="tf-dest",
        )

    def test_raises_config_error_listing_every_missing_value(self) -> None:
        with patch("tests.common.config._terraform_output", return_value=None):
            with pytest.raises(ConfigError) as exc_info:
                load_deployment_config()

        message = str(exc_info.value)
        assert ENV_FUNCTION_URL in message
        assert ENV_SOURCE_BUCKET in message
        assert ENV_DEST_BUCKET in message

    def test_partial_resolution_still_reports_only_whats_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(ENV_FUNCTION_URL, "https://from-env/fn")

        with patch("tests.common.config._terraform_output", return_value=None):
            with pytest.raises(ConfigError) as exc_info:
                load_deployment_config()

        # The "missing for" list (before the usage-example section) must
        # name only the two values that actually failed to resolve.
        missing_for_line = str(exc_info.value).splitlines()[0]
        assert ENV_FUNCTION_URL not in missing_for_line
        assert ENV_SOURCE_BUCKET in missing_for_line
        assert ENV_DEST_BUCKET in missing_for_line

    def test_terraform_command_failure_is_treated_as_unresolved(self) -> None:
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="terraform", timeout=30),
        ):
            with pytest.raises(ConfigError):
                load_deployment_config()

    def test_terraform_nonzero_exit_is_treated_as_unresolved(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["terraform", "output", "-raw", "x"],
            returncode=1,
            stdout="",
            stderr="no state file",
        )
        with patch("subprocess.run", return_value=completed):
            with pytest.raises(ConfigError):
                load_deployment_config()
