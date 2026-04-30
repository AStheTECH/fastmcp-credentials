from __future__ import annotations
from datetime import datetime, timedelta, timezone
import pytest
from fastmcp_credentials.types import ResolvedCredential, CredentialError, CredentialNotFoundError


class TestIsExpired:
    def test_no_expires_at_returns_false(self):
        assert not ResolvedCredential(type="static").is_expired()

    def test_far_future_returns_false(self):
        cred = ResolvedCredential(
            type="oauth",
            expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
        )
        assert not cred.is_expired()

    def test_past_expiry_returns_true(self):
        cred = ResolvedCredential(
            type="oauth",
            expires_at=datetime.now(tz=timezone.utc) - timedelta(seconds=1),
        )
        assert cred.is_expired()

    def test_within_60s_buffer_is_considered_expired(self):
        # 59 s from now is inside the 60-second safety buffer
        cred = ResolvedCredential(
            type="oauth",
            expires_at=datetime.now(tz=timezone.utc) + timedelta(seconds=59),
        )
        assert cred.is_expired()

    def test_just_outside_buffer_is_not_expired(self):
        cred = ResolvedCredential(
            type="oauth",
            expires_at=datetime.now(tz=timezone.utc) + timedelta(seconds=61),
        )
        assert not cred.is_expired()

    def test_naive_datetime_treated_as_utc(self):
        # A naive datetime well in the past should still be expired
        cred = ResolvedCredential(
            type="oauth",
            expires_at=datetime(2000, 1, 1),  # naive — no tzinfo
        )
        assert cred.is_expired()


class TestExceptions:
    def test_not_found_includes_credential_id_in_message(self):
        exc = CredentialNotFoundError("cred_abc123")
        assert "cred_abc123" in str(exc)

    def test_not_found_stores_credential_id_attribute(self):
        exc = CredentialNotFoundError("cred_abc123")
        assert exc.credential_id == "cred_abc123"

    def test_not_found_is_subclass_of_credential_error(self):
        assert issubclass(CredentialNotFoundError, CredentialError)

    def test_credential_error_is_subclass_of_exception(self):
        assert issubclass(CredentialError, Exception)


class TestResolvedCredential:
    def test_extra_defaults_to_empty_dict(self):
        assert ResolvedCredential(type="static").extra == {}

    def test_all_fields_are_optional_except_type(self):
        cred = ResolvedCredential(type="oauth")
        assert cred.access_token is None
        assert cred.refresh_token is None
        assert cred.client_id is None
        assert cred.client_secret is None
        assert cred.token_uri is None
        assert cred.scopes is None
        assert cred.expires_at is None
        assert cred.api_key is None

    def test_extra_dict_is_not_shared_between_instances(self):
        a = ResolvedCredential(type="static")
        b = ResolvedCredential(type="static")
        a.extra["key"] = "val"
        assert "key" not in b.extra
