from __future__ import annotations
import pytest
from fastmcp_credentials.config import get_mode, CredentialMode


def test_default_mode_is_oss_when_env_var_absent(monkeypatch):
    monkeypatch.delenv("FASTMCP_CREDENTIAL_MODE", raising=False)
    assert get_mode() == CredentialMode.OSS


def test_explicit_oss_value(monkeypatch):
    monkeypatch.setenv("FASTMCP_CREDENTIAL_MODE", "oss")
    assert get_mode() == CredentialMode.OSS


def test_hosted_value(monkeypatch):
    monkeypatch.setenv("FASTMCP_CREDENTIAL_MODE", "hosted")
    assert get_mode() == CredentialMode.HOSTED


def test_value_is_lowercased_before_parsing(monkeypatch):
    monkeypatch.setenv("FASTMCP_CREDENTIAL_MODE", "HOSTED")
    assert get_mode() == CredentialMode.HOSTED


def test_value_is_stripped_before_parsing(monkeypatch):
    monkeypatch.setenv("FASTMCP_CREDENTIAL_MODE", "  hosted  ")
    assert get_mode() == CredentialMode.HOSTED


def test_invalid_value_raises_value_error(monkeypatch):
    monkeypatch.setenv("FASTMCP_CREDENTIAL_MODE", "vault")
    with pytest.raises(ValueError, match="FASTMCP_CREDENTIAL_MODE"):
        get_mode()


def test_invalid_value_error_lists_valid_options(monkeypatch):
    monkeypatch.setenv("FASTMCP_CREDENTIAL_MODE", "invalid")
    with pytest.raises(ValueError) as exc_info:
        get_mode()
    msg = str(exc_info.value)
    assert "oss" in msg
    assert "hosted" in msg


def test_credential_mode_oss_value():
    assert CredentialMode.OSS.value == "oss"


def test_credential_mode_hosted_value():
    assert CredentialMode.HOSTED.value == "hosted"
