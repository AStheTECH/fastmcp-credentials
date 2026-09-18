# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.2.0] — 2026-09-18

### Changed

- **Breaking dependency floor:** now requires `fastmcp==4.0.5` exactly (previously
  `fastmcp>=3.2.4,<4.0.0`). This package targets FastMCP 4 / MCP Python SDK v2 and
  the modern, stateless `2026-07-28` protocol only — `fastmcp<4.0.0` and the
  legacy handshake-era protocol are no longer supported.
- `fastmcp` is now pinned to an **exact version**, not a range. Every previous
  release (and every MewCP server consuming this package) declared `fastmcp`
  with an open-ended floor (`>=3.2.4,<4.0.0` here; `>=0.1.0` fleet-wide), which
  meant a dependency resolution could silently pick up any future release. From
  this release on, moving to a new FastMCP version means bumping this package's
  pin and publishing a new release — never an implicit side effect of an
  unrelated redeploy.

### Public API

No changes. `CredentialMiddleware`, `get_credentials()`, `EnvCredentialBackend`,
`HeaderCredentialBackend`, `ResolvedCredential`, and the exception hierarchy are
unchanged — this is a dependency and packaging update only. No source changes
were required in `fastmcp_credentials` itself: `fastmcp.server.middleware`
(`Middleware`, `MiddlewareContext`) and `fastmcp.server.dependencies`
(`get_http_request`) resolve identically under FastMCP 4, and the package never
uses `Context`/`ctx`, so it has no exposure to FastMCP 4's `Context`-related
breaking changes.

### Added

- `tests/test_integration_http.py` — end-to-end tests against a real `FastMCP`
  instance mounted as a stateless Streamable HTTP ASGI app, driven with real
  HTTP requests (no `initialize` handshake, no session id). Covers both the
  `static` and `oauth` credential paths via `HeaderCredentialBackend`, confirms
  `MissingCredentialHeaderError` surfaces correctly as a JSON-RPC error, and
  stress-tests `ContextVar` isolation under concurrent stateless requests.

### Migration notes

Consumers only need to bump their own `fastmcp` pin to `4.0.5` (or repin their
`fastmcp-credentials` dependency to `>=0.2.0,<0.3.0`, per this project's
existing minor-version pinning convention) and redeploy — no code changes are
required.

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
