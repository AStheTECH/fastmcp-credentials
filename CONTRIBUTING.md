# Contributing to fastmcp-credentials

## Overview

fastmcp-credentials is a security-critical middleware library. Contributions are welcome, but correctness and security take precedence over velocity. If you are making changes that touch credential resolution, storage, or request isolation, expect thorough review.

This package handles sensitive data at runtime. All contributors are expected to understand the security model before proposing changes.

---

## Ways to Contribute

- **Bug fixes** — especially around credential isolation, backend errors, or middleware behavior
- **New credential backends** — AWS Secrets Manager, HashiCorp Vault, GCP Secret Manager, Azure Key Vault, etc.
- **OAuth improvements** — token refresh, scope handling, provider-specific flows
- **Documentation** — usage examples, backend integration guides, security clarifications
- **Test coverage** — unit tests, integration tests, edge case handling

---

## Development Setup

```bash
git clone https://github.com/AStheTECH/fastmcp-credentials.git
cd fastmcp-credentials

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install with development dependencies
pip install -e ".[dev]"

# Run the test suite
pytest
```

---

## Coding Standards

- **Type hints are required** on all function signatures and class attributes
- Follow PEP 8; use a formatter (e.g., `black`, `ruff`) before submitting
- Keep concerns clearly separated — backends, middleware, and resolution logic should not bleed into each other
- **Never log or surface credentials** in error messages, tracebacks, or debug output, even partially
- Raise typed exceptions rather than generic `Exception` where possible
- New backends must implement the existing `CredentialBackend` interface

---

## Pull Request Guidelines

- Keep PRs small and focused — one concern per PR
- Every PR that adds or modifies behavior must include tests
- Include a clear description of what changed and why
- Reference related issues if applicable
- Security-sensitive changes (credential resolution paths, isolation logic, backend implementations) require explicit review notes explaining the threat model impact

Do not open PRs that:
- Introduce credential logging (even at DEBUG level)
- Relax type constraints on credential-carrying objects
- Bypass the request-scoped isolation mechanism

---

## Review Expectations

Maintainers will review for:

1. **Correctness** — does it behave as documented?
2. **Security** — does it preserve isolation guarantees?
3. **Type safety** — are types complete and accurate?
4. **Test coverage** — are edge cases covered?

Reviews may take time. Security-related feedback is not negotiable. Changes may be requested before merge even if the implementation is functionally correct.
