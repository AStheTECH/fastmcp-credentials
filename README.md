# fastmcp-credentials

Secure credential injection middleware for [FastMCP](https://github.com/jlowin/fastmcp) servers.

Keeps secrets completely out of the LLM — credentials travel in HTTP headers, are resolved server-side, and injected into tools transparently. The AI agent never sees tokens, API keys, or client secrets.

## How it works

1. A request arrives with an `X-Credential-ID` header (e.g. `cred_abc123`).
2. `CredentialMiddleware` intercepts the tool call, resolves the credential from the configured backend, and stores it in a request-scoped `ContextVar`.
3. Your tool calls `get_credentials()` — a plain sync function, no `await`, no `ctx` — to get the resolved credential.
4. After the tool returns, the `ContextVar` is reset. Credentials never leak between requests.

The LLM only ever sees your tool's business parameters. Auth is invisible to it by design.

---

## Installation

```bash
pip install fastmcp-credentials
```

For the MongoDB-backed backend (hosted / production deployments):

```bash
pip install 'fastmcp-credentials[hosted]'
```

---

## Quick start — Static API key (default)

The most common case: your service uses a single API key.

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

`EnvCredentialBackend` defaults to `static` mode. No `CRED_TYPE` env var needed unless you want OAuth.

---

## Extra credential fields

Some providers require more than the standard fields — a key + secret, a tenant ID alongside an OAuth token, etc. `{PREFIX}EXTRA_{NAME}` env vars work for **both** `static` and `oauth` types and are collected into `cred.extra`:

```bash
# Works with static auth
export MYSERVICE_API_KEY=pk-live-abc123
export MYSERVICE_EXTRA_API_SECRET=sk-live-xyz789
export MYSERVICE_EXTRA_ACCOUNT_ID=acct_42

# Works with OAuth too
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

---

## Quick start — OAuth

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

## Using a credentials file

For local development with multiple credentials, use `FileCredentialBackend` and a JSON file.

**Flat format (single credential):**

```json
{
  "type": "static",
  "api_key": "sk-abc123",
  "extra": { "account_id": "acct_42" }
}
```

**Keyed format (multiple credentials) — `X-Credential-ID` selects the entry:**

```json
{
  "cred_user1": { "type": "static", "api_key": "sk-user1key" },
  "cred_user2": { "type": "oauth",  "access_token": "ya29...", "refresh_token": "1//..." }
}
```

```python
from fastmcp_credentials import CredentialMiddleware, FileCredentialBackend

backend = FileCredentialBackend("credentials.json")
mcp = FastMCP("My Service", middleware=[CredentialMiddleware(backend)])
```

---

## MongoDB backend

`MongoDBCredentialBackend` stores credentials in MongoDB with AES-256-GCM encryption at rest. Use this for multi-user or production deployments where credentials must be stored server-side.

```bash
pip install 'fastmcp-credentials[hosted]'
```

```python
import os
from fastmcp_credentials import CredentialMiddleware, MongoDBCredentialBackend

backend = MongoDBCredentialBackend(
    db_url=os.environ["DB_URL"],
    # db_name defaults to CRED_DB_NAME env var, then "credentials"
    # encryption_key defaults to CRED_ENCRYPTION_KEY env var
)
mcp = FastMCP("My Service", middleware=[CredentialMiddleware(backend)])
```

Generate an encryption key:

```bash
python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
```

Provider-specific fields that don't map to standard OAuth names can be stored in the document's `encrypted_extra` object (a JSON blob encrypted as a single unit) and are surfaced in `cred.extra`.

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

## Implementing a custom backend

Implement `CredentialBackend` to pull credentials from any source — AWS Secrets Manager, HashiCorp Vault, a database, or your own API:

```python
from fastmcp_credentials import CredentialBackend, ResolvedCredential, CredentialNotFoundError

class MyCustomBackend(CredentialBackend):
    async def resolve(self, credential_id: str) -> ResolvedCredential:
        data = await my_secrets_client.get(credential_id)
        if not data:
            raise CredentialNotFoundError(credential_id)
        return ResolvedCredential(
            type="static",
            api_key=data["api_key"],
            extra=data.get("extra", {}),
        )

backend = MyCustomBackend()
mcp = FastMCP("My Server", middleware=[CredentialMiddleware(backend)])
```

---

## Backends summary

| Backend | Best for |
|---|---|
| `EnvCredentialBackend` | Local dev, self-hosted single-user servers |
| `FileCredentialBackend` | Local dev with multiple credentials in a JSON file |
| `MongoDBCredentialBackend` | Multi-user / production — encrypted storage in MongoDB |
| Custom `CredentialBackend` | Any other secret store: Vault, AWS Secrets Manager, etc. |

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
python -m pytest tests/backends/test_mongodb.py::test_encrypt_decrypt_roundtrip
```

Run with verbose output:

```bash
python -m pytest -v
```

If you prefer to call `pytest` directly, make sure the environment that has it installed is activated first.

The suite is fully self-contained — no running MongoDB or external services required. The MongoDB backend tests mock the database and HTTP calls.

---

## License

MIT
