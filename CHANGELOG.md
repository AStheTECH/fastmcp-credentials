# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.0] — 2026-05-04

### Added

- `CredentialMiddleware` — FastMCP middleware that resolves credentials per request and stores them in a request-scoped `ContextVar`, preventing any leakage between concurrent requests.
- `get_credentials()` — synchronous accessor that retrieves the `ResolvedCredential` for the current request context; raises `CredentialNotFoundError` when called outside a middleware-wrapped request.
- `ResolvedCredential` dataclass — unified credential object supporting both static (API key) and OAuth credential types, including `is_expired()` with a 60-second safety buffer.
- `EnvCredentialBackend` — resolves credentials from environment variables using a configurable prefix (e.g. `MYSERVICE_`). Supports static API keys, full OAuth token sets, and arbitrary extra fields via `{PREFIX}EXTRA_{NAME}`.
- `HeaderCredentialBackend` — resolves credentials from gateway-injected HTTP headers (`X-MCP-Cred-*`). Supports JSON and base64-encoded JSON for the `X-MCP-Cred-Extra` header. Raises `MissingCredentialHeaderError` when neither `X-MCP-Cred-Access-Token` nor `X-MCP-Cred-Api-Key` is present.
- `CredentialMode` enum and `get_mode()` helper — runtime detection of `oss` vs. `hosted` deployment mode via the `FASTMCP_CREDENTIAL_MODE` environment variable.
- Custom exception hierarchy: `CredentialError` (base), `CredentialNotFoundError`, `MissingCredentialHeaderError`.
- PEP 561 `py.typed` marker — inline type annotations are exported and consumable by mypy and pyright.
- 71-test suite covering happy paths, error paths, context isolation, and edge cases (malformed headers, naive datetimes, empty prefixes, sequential requests).
