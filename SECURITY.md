# Security Policy

## Supported Versions

The latest release on the `main` branch receives active maintenance. Security fixes are backported only to the most recent minor version. Older versions are unsupported.

---

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Report vulnerabilities directly to the maintainers via email or private communication. Include:

- A clear description of the vulnerability
- Steps to reproduce or a proof-of-concept
- The potential impact and affected versions

You will receive acknowledgment within 72 hours. We aim to release a fix or mitigation within 14 days of a confirmed report, depending on severity and complexity.

---

## Security Model

fastmcp-credentials is designed around a single core guarantee: **credentials never reach the LLM**.

### How it works

1. Credentials are resolved from the configured backend — environment variables (`EnvCredentialBackend`) or gateway-injected HTTP headers (`HeaderCredentialBackend`) — entirely within the server process before any tool executes.
2. In gateway deployments, the gateway decrypts and refreshes credentials, then injects them as `X-MCP-Cred-*` headers. The LLM never handles these headers.
3. The middleware intercepts each tool call and resolves the credential from the backend.
4. The resolved credential is stored in a **request-scoped `ContextVar`** — it is accessible only within the execution context of that specific request.
5. The `ContextVar` is explicitly cleared in a `finally` block after the request completes, regardless of success or failure.

At no point does the credential value appear in the MCP message payload, tool arguments, or any structure visible to the LLM.

---

## Threat Model

### Protected Against

| Threat | Mitigation |
|--------|------------|
| Credential leakage to LLM | Credentials are never included in MCP protocol messages |
| Cross-request credential contamination | ContextVar isolation scopes credentials to a single request execution context |
| Multi-tenant credential confusion | Each request resolves its own credential by ID; no shared mutable state |

### Not Protected Against

The following are **outside the scope** of this library's guarantees:

- **Compromised host environment** — if the process, OS, or memory is compromised, credential values stored in ContextVars can be extracted
- **Malicious or misconfigured backends** — this library trusts the backend implementation to return correct credentials; a buggy or compromised backend can return wrong or leaked values
- **Misconfigured deployments** — if credentials are inadvertently included in tool descriptions, system prompts, or response bodies by the application layer, this library cannot prevent that
- **Insecure transport** — credentials in transit depend on the security of the HTTP layer; always use TLS in production

---

## Security Best Practices for Users

- **Use a secure backend in production.** The `EnvCredentialBackend` is appropriate for development and single-user self-hosted deployments. Production multi-user deployments should use a gateway with `HeaderCredentialBackend`, backed by a secrets manager (e.g., AWS Secrets Manager, HashiCorp Vault, GCP Secret Manager).
- **Rotate credentials regularly.** This library resolves credentials at request time; rotation does not require a restart.
- **Do not log request contexts.** Ensure your logging configuration does not capture ContextVar contents or raw HTTP headers.
- **Validate credential IDs.** If your backend performs lookups by ID, validate and sanitize the ID to prevent injection attacks.
- **Restrict backend access.** The process running the FastMCP server should have the minimum permissions necessary to access the credential store.
