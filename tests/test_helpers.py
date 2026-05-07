from __future__ import annotations
import pytest
from fastmcp_credentials.helpers import get_credentials
from fastmcp_credentials.middleware import _current_credential
from fastmcp_credentials.types import ResolvedCredential, CredentialError


def test_raises_when_no_credential_in_context():
    with pytest.raises(CredentialError, match="No credential"):
        get_credentials()


def test_returns_credential_set_in_context():
    cred = ResolvedCredential(type="static", fields={"apiKey": "sk-test"})
    token = _current_credential.set(cred)
    try:
        assert get_credentials() is cred
    finally:
        _current_credential.reset(token)


def test_multiple_calls_return_same_object():
    cred = ResolvedCredential(type="static", fields={"apiKey": "sk-test"})
    token = _current_credential.set(cred)
    try:
        assert get_credentials() is get_credentials()
    finally:
        _current_credential.reset(token)


def test_raises_again_after_context_is_reset():
    cred = ResolvedCredential(type="static", fields={"apiKey": "sk-test"})
    token = _current_credential.set(cred)
    _current_credential.reset(token)
    with pytest.raises(CredentialError):
        get_credentials()
