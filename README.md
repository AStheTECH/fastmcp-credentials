# fastmcp-credentials

Secure credential injection middleware for [FastMCP](https://github.com/jlowin/fastmcp) servers.

Keeps secrets completely out of the LLM — credentials are resolved server-side and injected into tools transparently. The AI agent never sees tokens, API keys, or client secrets.

---

## How it works

1. `CredentialMiddleware` intercepts every tool call and resolves credentials via the configured backend.
2. Credentials are stored in a request-scoped `ContextVar` — they never leak between concurrent requests.
3. Your tool calls `get_credentials()` — a plain synchronous function, no `await`, no `ctx` — to read them.
4. After the tool returns (or raises), the `ContextVar` is always reset in a `finally` block.

The LLM only ever sees your tool's business parameters. Auth is invisible to it by design.

---

## Installation

```bash
pip install fastmcp-credentials
```

Requires Python 3.11+ and FastMCP 3.x.

---

## Backends

| Backend | Best for |
|---|---|
| `EnvCredentialBackend` | Local development, self-hosted single-user servers |
| `HeaderCredentialBackend` | Gateway-managed multi-user deployments |

---

## Quick start — Static credentials (env vars)

Static credentials are arbitrary key/value fields loaded from environment variables. All fields are available on `cred.fields`.

```bash
# Option 1 — JSON object (recommended for multi-field providers):
export MYSERVICE_FIELDS='{"apiKey":"sk-abc123","secretKey":"xyz789"}'

# Option 2 — individual FIELD_<name> vars (useful with secrets managers):
export MYSERVICE_FIELD_apiKey=sk-abc123
export MYSERVICE_FIELD_secretKey=xyz789
```

```python
import requests
from fastmcp import FastMCP
from fastmcp_credentials import CredentialMiddleware, EnvCredentialBackend, get_credentials

backend = EnvCredentialBackend(prefix="MYSERVICE_")
mcp = FastMCP("My Service", middleware=[CredentialMiddleware(backend, "static")])

@mcp.tool()
def search(query: str) -> list:
    creds = get_credentials()
    response = requests.get(
        "https://api.myservice.com/search",
        headers={"Authorization": f"Bearer {creds.fields['apiKey']}"},
        params={"q": query},
    )
    return response.json()
```

---

## Quick start — OAuth (env vars)

For OAuth tokens, set `{PREFIX}CRED_TYPE=oauth`:

```bash
export MYSERVICE_ACCESS_TOKEN=ya29...
export MYSERVICE_REFRESH_TOKEN=1//...
export MYSERVICE_CLIENT_ID=your_client_id
export MYSERVICE_CLIENT_SECRET=your_client_secret
export MYSERVICE_TOKEN_URI=https://auth.myservice.com/token
export MYSERVICE_SCOPES=read write
```

```python
backend = EnvCredentialBackend(prefix="MYSERVICE_")
mcp = FastMCP("My Service", middleware=[CredentialMiddleware(backend, "oauth")])

@mcp.tool()
def list_items(folder_id: str) -> list:
    creds = get_credentials()
    response = requests.get(
        "https://api.myservice.com/items",
        headers={"Authorization": f"Bearer {creds.access_token}"},
        params={"folder": folder_id},
    )
    return response.json()
```

---

## Quick start — Gateway-injected credentials (hosted mode)

For multi-user deployments where a gateway decrypts, refreshes, and injects credentials as HTTP headers before forwarding requests to your MCP server:

```python
import requests
from fastmcp import FastMCP
from fastmcp_credentials import CredentialMiddleware, HeaderCredentialBackend, get_credentials

backend = HeaderCredentialBackend()
mcp = FastMCP("My Service", middleware=[CredentialMiddleware(backend, "oauth")])

@mcp.tool()
def call_api(resource_id: str) -> dict:
    creds = get_credentials()
    return requests.get(
        f"https://api.example.com/resources/{resource_id}",
        headers={"Authorization": f"Bearer {creds.access_token}"},
    ).json()
```

The gateway sends these headers — no tool parameters, no LLM involvement:

```
X-MCP-Cred-Access-Token: ya29...
X-MCP-Cred-Fields: {"apiKey":"sk-...","secretKey":"..."}
X-MCP-Cred-Scopes: read write
X-MCP-Cred-Extra: {"tenant_id": "..."}
X-MCP-Cred-Expires-At: 2026-05-04T12:00:00Z
```

Tools access credentials identically to env-based mode via `get_credentials()`.

---

## OAuth extras

Some OAuth providers include non-sensitive metadata alongside the token — a data-centre region, a workspace identifier, etc. These are collected into `cred.extra` for OAuth credentials only.

**Env vars:** use the `{PREFIX}EXTRA_{NAME}` pattern.

```bash
export MYSERVICE_CRED_TYPE=oauth
export MYSERVICE_ACCESS_TOKEN=ya29...
export MYSERVICE_EXTRA_DC=us10
export MYSERVICE_EXTRA_WORKSPACE=my-workspace
```

```python
@mcp.tool()
def call_api() -> dict:
    creds = get_credentials()
    base_url = f"https://{creds.extra['dc']}.api.example.com"
    return requests.get(base_url, headers={"Authorization": f"Bearer {creds.access_token}"}).json()
```

**Gateway mode:** the gateway encodes extras in the `X-MCP-Cred-Extra` header as a JSON object.

---

## Selecting a backend based on deployment mode

If you need to switch backends at runtime (e.g. env vars locally, header-injected in production), use the `get_mode()` helper which reads the `FASTMCP_CREDENTIAL_MODE` environment variable:

```python
from fastmcp_credentials import CredentialMiddleware, EnvCredentialBackend, HeaderCredentialBackend, get_mode, CredentialMode

if get_mode() == CredentialMode.HOSTED:
    backend = HeaderCredentialBackend()
else:
    backend = EnvCredentialBackend(prefix="MYSERVICE_")

mcp = FastMCP("My Service", middleware=[CredentialMiddleware(backend, "oauth")])
```

```bash
# Local / self-hosted (default — no env var needed)
# FASTMCP_CREDENTIAL_MODE=oss

# Production behind a gateway
export FASTMCP_CREDENTIAL_MODE=hosted
```

---

## The `ResolvedCredential` object

`get_credentials()` always returns a `ResolvedCredential` dataclass, regardless of which backend is used:

```python
@dataclass
class ResolvedCredential:
    type: Literal["static", "oauth"]

    # Static auth — all provider fields by name
    fields: dict[str, str]

    # OAuth
    access_token: str | None
    refresh_token: str | None
    client_id: str | None
    client_secret: str | None
    token_uri: str | None
    scopes: list[str] | None
    expires_at: datetime | None

    # OAuth metadata only (e.g. dc, workspace). Empty for static credentials.
    extra: dict[str, Any]

    def is_expired(self) -> bool: ...
```

`is_expired()` returns `True` if the access token has expired or expires within the next 60 seconds.

---

## Environment variable reference

All variables use the prefix you pass to `EnvCredentialBackend(prefix="...")`.

| Variable | Default | Description |
|---|---|---|
| `{PREFIX}FIELDS` | — | JSON object with all static fields, e.g. `{"apiKey":"...","secretKey":"..."}` |
| `{PREFIX}FIELD_{NAME}` | — | Individual static field (key name preserved as-is) → `cred.fields["NAME"]` |
| `{PREFIX}EXTRA_{NAME}` | — | OAuth metadata only → `cred.extra["name"]` |
| `{PREFIX}ACCESS_TOKEN` | — | OAuth access token |
| `{PREFIX}REFRESH_TOKEN` | — | OAuth refresh token |
| `{PREFIX}CLIENT_ID` | — | OAuth client identifier |
| `{PREFIX}CLIENT_SECRET` | — | OAuth client secret |
| `{PREFIX}TOKEN_URI` | — | Token refresh endpoint URL |
| `{PREFIX}SCOPES` | — | Space-separated OAuth scopes |
| `{PREFIX}EXPIRES_AT` | — | ISO 8601 token expiry (e.g. `2026-05-04T12:00:00+00:00`) |

`{PREFIX}FIELDS` takes priority over individual `{PREFIX}FIELD_{NAME}` vars when both are set.

---

## Header reference (gateway-injected mode)

When using `HeaderCredentialBackend`, the gateway injects these headers. At least one of the first two must be present.

| Header | Required for | Description |
|---|---|---|
| `X-MCP-Cred-Access-Token` | `"oauth"` type | OAuth access token |
| `X-MCP-Cred-Fields` | `"static"` type | JSON object with all static credential fields |
| `X-MCP-Cred-Scopes` | No | Space-separated string of OAuth scopes |
| `X-MCP-Cred-Extra` | No | JSON object with OAuth provider metadata |
| `X-MCP-Cred-Expires-At` | No | Token expiry as ISO 8601 UTC timestamp |

The required header depends on the credential type configured in `CredentialMiddleware`. If the type-appropriate header is missing, a `MissingCredentialHeaderError` is raised.

---

## Running the tests

Clone the repo and install with the `dev` extras:

```bash
git clone https://github.com/AStheTECH/fastmcp-credentials.git
cd fastmcp-credentials
pip install -e ".[dev]"
```

Run the full suite:

```bash
python -m pytest
```

Run a specific file or test:

```bash
python -m pytest tests/backends/test_env.py
python -m pytest tests/backends/test_headers.py::test_parse_scopes
```

Run with verbose output:

```bash
python -m pytest -v
```

---

## License

Apache-2.0
