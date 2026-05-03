# fastmcp-credentials

Secure credential injection middleware for [FastMCP](https://github.com/jlowin/fastmcp) servers.

Keeps secrets completely out of the LLM — credentials are resolved server-side and injected into tools transparently. The AI agent never sees tokens, API keys, or client secrets.

## How it works

1. `CredentialMiddleware` intercepts tool calls and resolves credentials via the configured backend.
2. Credentials are stored in a request-scoped `ContextVar` (no leaking between requests).
3. Your tool calls `get_credentials()` — a plain sync function, no `await`, no `ctx` — to access them.
4. After the tool returns, the `ContextVar` is reset.

The LLM only ever sees your tool's business parameters. Auth is invisible to it by design.

---

## Installation

```bash
pip install fastmcp-credentials
```

---

## Quick start — Static API key (environment variables)

The most common case: your service uses a single API key from environment variables.

```bash
export MYSERVICE_API_KEY=sk-abc123...
```

```python
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

## Quick start — OAuth (environment variables)

For OAuth tokens, set `CRED_TYPE=oauth`:

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

## Hosted mode — Gateway-injected credentials

For hosted deployments where a gateway injects resolved credentials as HTTP headers:

```python
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

The gateway sends these headers (no tool parameters needed):

```
X-Mewcp-Access-Token: ya29...
X-Mewcp-Api-Key: sk-...
X-Mewcp-Scopes: read,write
X-Mewcp-Extra: {"tenant_id":"..."}
X-Mewcp-Expires-At: 2026-05-04T12:00:00Z
```

Tools access credentials identically to env-based mode via `get_credentials()`.

---

## Extra credential fields

Some providers require more than the standard fields — a key + secret, a tenant ID alongside an OAuth token, etc. Extra fields work with **both** `static` and `oauth` types via `{PREFIX}EXTRA_{NAME}` env vars and are collected into `cred.extra`:

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

Or for gateway-injected mode, the gateway includes them in `X-Mewcp-Extra`.

---

## The `ResolvedCredential` object

`get_credentials()` returns a `ResolvedCredential` dataclass:

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

---

## Environment variable reference

All variables use the prefix you set in `EnvCredentialBackend(prefix="...")`.

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
| `{PREFIX}EXPIRES_AT` | — | ISO 8601 token expiry (e.g. `2026-04-24T12:00:00+00:00`) |

---

## Header reference (gateway-injected mode)

When using `HeaderCredentialBackend`, the gateway sends these headers:

| Header | Description |
|---|---|
| `X-Mewcp-Access-Token` | OAuth access token |
| `X-Mewcp-Api-Key` | Static API key / PAT |
| `X-Mewcp-Scopes` | Scopes (space-separated or JSON array) |
| `X-Mewcp-Extra` | Extra fields (JSON object or base64-encoded JSON) |
| `X-Mewcp-Expires-At` | Token expiry (ISO 8601 UTC timestamp) |

At least one of `X-Mewcp-Access-Token` or `X-Mewcp-Api-Key` must be present.

---

## Backends summary

| Backend | Mode | Best for |
|---|---|---|
| `EnvCredentialBackend` | Self-hosted | Local dev, single-user servers, env var config |
| `HeaderCredentialBackend` | Hosted | Gateway-injected credentials, multi-user deployments |

---

## Running the tests

Clone the repo and install with the `dev` extras:

```bash
git clone https://github.com/your-org/fastmcp-credentials.git
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

MIT
