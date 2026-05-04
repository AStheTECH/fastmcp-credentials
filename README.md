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

## Quick start — Static API key (env vars)

The most common case: your service uses a single API key loaded from environment variables.

```bash
export MYSERVICE_API_KEY=sk-abc123...
```

```python
import requests
from fastmcp import FastMCP
from fastmcp_credentials import CredentialMiddleware, EnvCredentialBackend, get_credentials

backend = EnvCredentialBackend(prefix="MYSERVICE_")
mcp = FastMCP("My Service", middleware=[CredentialMiddleware(backend)])

@mcp.tool()
def search(query: str) -> list:
    creds = get_credentials()
    response = requests.get(
        "https://api.myservice.com/search",
        headers={"Authorization": f"Bearer {creds.api_key}"},
        params={"q": query},
    )
    return response.json()
```

---

## Quick start — OAuth (env vars)

For OAuth tokens, set `{PREFIX}CRED_TYPE=oauth`:

```bash
export MYSERVICE_CRED_TYPE=oauth
export MYSERVICE_ACCESS_TOKEN=ya29...
export MYSERVICE_REFRESH_TOKEN=1//...
export MYSERVICE_CLIENT_ID=your_client_id
export MYSERVICE_CLIENT_SECRET=your_client_secret
export MYSERVICE_TOKEN_URI=https://auth.myservice.com/token
export MYSERVICE_SCOPES=read,write
```

```python
backend = EnvCredentialBackend(prefix="MYSERVICE_")
mcp = FastMCP("My Service", middleware=[CredentialMiddleware(backend)])

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
mcp = FastMCP("My Service", middleware=[CredentialMiddleware(backend)])

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
X-MCP-Cred-Api-Key: sk-...
X-MCP-Cred-Scopes: read,write
X-MCP-Cred-Extra: {"tenant_id": "..."}
X-MCP-Cred-Expires-At: 2026-05-04T12:00:00Z
```

Tools access credentials identically to env-based mode via `get_credentials()`.

---

## Extra credential fields

Some providers require more than the standard fields — a signing secret alongside an API key, a tenant ID alongside an OAuth token, etc. Extra fields work with **both** `static` and `oauth` types and are collected into `cred.extra`.

**Env vars:** use the `{PREFIX}EXTRA_{NAME}` pattern.

```bash
# Static auth with extras
export MYSERVICE_API_KEY=pk-live-abc123
export MYSERVICE_EXTRA_API_SECRET=sk-live-xyz789
export MYSERVICE_EXTRA_ACCOUNT_ID=acct_42

# OAuth with extras
export MYSERVICE_CRED_TYPE=oauth
export MYSERVICE_ACCESS_TOKEN=ya29...
export MYSERVICE_EXTRA_TENANT_ID=tenant-xyz
```

```python
@mcp.tool()
def create_charge(amount: int) -> dict:
    creds = get_credentials()
    return client.charge(
        api_key=creds.api_key,
        secret=creds.extra["api_secret"],
        account=creds.extra["account_id"],
        amount=amount,
    )
```

**Gateway mode:** the gateway encodes extras in the `X-MCP-Cred-Extra` header as a JSON object or base64-encoded JSON.

---

## Selecting a backend based on deployment mode

If you need to switch backends at runtime (e.g. env vars locally, header-injected in production), use the `get_mode()` helper which reads the `FASTMCP_CREDENTIAL_MODE` environment variable:

```python
from fastmcp_credentials import CredentialMiddleware, EnvCredentialBackend, HeaderCredentialBackend, get_mode, CredentialMode

if get_mode() == CredentialMode.HOSTED:
    backend = HeaderCredentialBackend()
else:
    backend = EnvCredentialBackend(prefix="MYSERVICE_")

mcp = FastMCP("My Service", middleware=[CredentialMiddleware(backend)])
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

    # Static auth
    api_key: str | None

    # OAuth
    access_token: str | None
    refresh_token: str | None
    client_id: str | None
    client_secret: str | None
    token_uri: str | None
    scopes: list[str] | None
    expires_at: datetime | None

    # Provider-specific extras (populated by any backend)
    extra: dict

    def is_expired(self) -> bool: ...
```

`is_expired()` returns `True` if the access token has expired or expires within the next 60 seconds.

---

## Environment variable reference

All variables use the prefix you pass to `EnvCredentialBackend(prefix="...")`.

| Variable | Default | Description |
|---|---|---|
| `{PREFIX}CRED_TYPE` | `static` | `static` for API keys, `oauth` for OAuth tokens |
| `{PREFIX}API_KEY` | — | Primary API key (used when `CRED_TYPE=static`) |
| `{PREFIX}EXTRA_{NAME}` | — | Extra fields for any auth type → `cred.extra["name"]` |
| `{PREFIX}ACCESS_TOKEN` | — | OAuth access token |
| `{PREFIX}REFRESH_TOKEN` | — | OAuth refresh token |
| `{PREFIX}CLIENT_ID` | — | OAuth client identifier |
| `{PREFIX}CLIENT_SECRET` | — | OAuth client secret |
| `{PREFIX}TOKEN_URI` | — | Token refresh endpoint URL |
| `{PREFIX}SCOPES` | — | Comma-separated OAuth scopes |
| `{PREFIX}EXPIRES_AT` | — | ISO 8601 token expiry (e.g. `2026-05-04T12:00:00+00:00`) |

---

## Header reference (gateway-injected mode)

When using `HeaderCredentialBackend`, the gateway injects these headers. At least one of the first two must be present.

| Header | Required | Description |
|---|---|---|
| `X-MCP-Cred-Access-Token` | One of these | OAuth access token |
| `X-MCP-Cred-Api-Key` | One of these | Static API key / PAT |
| `X-MCP-Cred-Scopes` | No | Comma-separated string or JSON array of scopes |
| `X-MCP-Cred-Extra` | No | JSON object or base64-encoded JSON with provider-specific fields |
| `X-MCP-Cred-Expires-At` | No | Token expiry as ISO 8601 UTC timestamp |

If neither `X-MCP-Cred-Access-Token` nor `X-MCP-Cred-Api-Key` is present, a `MissingCredentialHeaderError` is raised.

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
