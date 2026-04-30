# Roadmap

This document outlines the planned direction for fastmcp-credentials. Items are listed roughly by priority within each phase. This is not a commitment to specific release dates.

---

## Short-Term

- **Expand test coverage** — edge cases in credential resolution, ContextVar cleanup on exception paths, backend error propagation
- **Additional backend integrations**
  - AWS Secrets Manager
  - HashiCorp Vault (KV v1 and v2)
  - GCP Secret Manager
  - Azure Key Vault
- **Improved documentation** — per-backend integration guides, deployment examples, annotated configuration reference
- **CI hardening** — enforce type checking (`mypy --strict`) and linting in CI pipeline

---

## Mid-Term

- **OAuth token auto-refresh** — detect expiry and transparently refresh tokens without requiring client re-authentication
- **Credential caching** — optional TTL-based in-process cache to reduce backend round-trips; cache must respect request isolation guarantees
- **Observability hooks** — structured logging (no credential values), optional tracing integration (OpenTelemetry), resolution latency metrics
- **Async backend support** — ensure all backends work correctly under async FastMCP server contexts with proper concurrency handling

---

## Long-Term

- **Policy enforcement layer** — allow/deny rules on which credential IDs a given client or role can resolve
- **Enterprise backend integrations** — CyberArk, Thales, and other enterprise secrets management platforms
- **Multi-region credential resolution** — routing and fallback strategies for distributed deployments
- **Audit logging** — tamper-evident log of credential resolution events for compliance use cases

---

## Contribution Opportunities

The following areas are well-suited for external contributors:

| Area | Notes |
|------|-------|
| New backends | Follow the `CredentialBackend` interface; include tests and a usage example |
| OAuth provider support | Provider-specific flows, token refresh, scope mapping |
| Documentation | Backend guides, deployment patterns, security hardening walkthroughs |
| Test coverage | Async edge cases, error paths, multi-tenant isolation scenarios |
| CI/tooling | Benchmark harness, fuzz testing for backend lookup inputs |

If you are planning a significant contribution (new backend, architecture change), open an issue first to align on the approach before writing code.
