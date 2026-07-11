# cocktail-recipes-mcp

Dockerized Python 3.11 MCP server for the `Aephir/cocktail-recipes` REST API.

This server is designed for Claude Desktop and other MCP clients. It authenticates against the cocktail app via session-cookie login (`POST /api/auth/login`) and uses REST-only calls.

## Features

- Python 3.11 MCP server with typed models and validation
- Self-contained OAuth 2.1 authorization server for remote Claude connectors
- Session-cookie auth with automatic re-login on `401`
- Safe retries for idempotent calls (read-only and dry-run operations)
- No blind retries for non-idempotent apply calls
- Dry-run safety defaults for destructive tools
- Structured response and error schema
- Capability probing tool for backend endpoint readiness
- Operation log tool for recent MCP actions

## Implemented Tools

- `list_recipes`
- `get_recipe`
- `create_recipe` (defaults `dry_run=true`)
- `update_recipe` (defaults `dry_run=true`)
- `delete_recipe` (defaults `dry_run=true`)
- `list_ingredients`
- `list_tools`
- `merge_ingredients` (`dry_run=true` default)
- `merge_tools` (`dry_run=true` default)
- `recategorize_recipes` (`dry_run=true` default)
- `update_tags_bulk` (`dry_run=true` default)
- `operation_log_recent`
- `api_capabilities`

## Safety Behavior

All destructive tools default to `dry_run=true` (create/update/delete/merge/recategorize/tag bulk).

To apply, pass explicit `dry_run=false`.

Each destructive tool returns:
- preview (`affected` IDs and count)
- `apply_executed` boolean
- backend result payload

If backend admin endpoints are not available yet, tool responses return structured `not_implemented` with an actionable message.

## Required Environment Variables

- `COCKTAIL_API_BASE_URL`
- `COCKTAIL_API_USERNAME`
- `COCKTAIL_API_PASSWORD`
- `PUBLIC_BASE_URL` when using `streamable-http`
- `AUTH_USERNAME` when using `streamable-http`
- `AUTH_PASSWORD` when using `streamable-http`

Optional variables are in `.env.example`.

## Transport Modes

- `stdio` (default in `.env.example`): process-local MCP over stdin/stdout, no published port.
- `streamable-http`: network-reachable MCP over HTTP with embedded OAuth 2.1, requires a published port or reverse proxy.

For Claude running on a different machine, use `streamable-http`.

## Embedded OAuth

When `MCP_TRANSPORT=streamable-http`, this container acts as both:

- the OAuth authorization server
- the OAuth-protected MCP resource server

Implemented endpoints:

- `GET /.well-known/oauth-authorization-server`
- `GET /.well-known/oauth-protected-resource`
- `GET /.well-known/jwks.json`
- `POST /register`
- `GET|POST /authorize`
- `POST /token`
- `POST|GET /mcp` protected by `Authorization: Bearer <token>`

OAuth details:

- Authorization Code flow with PKCE (`S256` required)
- Dynamic Client Registration for public clients (`token_endpoint_auth_method: none`)
- Built-in login form and consent screen using `AUTH_USERNAME` and `AUTH_PASSWORD`
- JWT access tokens signed by a persisted RSA key
- Rotating refresh tokens for public clients

Persisted OAuth state:

- signing key
- registered clients
- authorization codes
- refresh tokens

## Local Run

1. Create env file:

```bash
cp .env.example .env
```

2. Install dependencies and run:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .[test]
python -m cocktail_recipes_mcp.main
```

## Docker Run

Build image:

```bash
docker build -t cocktail-recipes-mcp:latest .
```

Run container:

```bash
docker run --rm -i --env-file .env cocktail-recipes-mcp:latest
```

Compose example:

```bash
docker compose up --build cocktail-recipes-mcp
```

Note: `docker-compose.yml` reads values from environment variables. For local CLI usage, export them or place them in a local `.env` file before running `docker compose`.

For remote clients, set `MCP_TRANSPORT=streamable-http`, configure `PUBLIC_BASE_URL`, `AUTH_USERNAME`, `AUTH_PASSWORD`, and publish `MCP_HTTP_PUBLISH_PORT`.
## Portainer Deployment (Recommended)

Use this when you run both the cocktail app and this MCP server as containers.

1. Deploy both services on the same Docker network.
2. Set MCP environment variables in Portainer for the MCP service:
   - `COCKTAIL_API_BASE_URL`
   - `COCKTAIL_API_USERNAME`
   - `COCKTAIL_API_PASSWORD`
  - `MCP_TRANSPORT=streamable-http`
  - `MCP_HTTP_HOST=0.0.0.0`
  - `MCP_HTTP_PORT=8000`
  - `MCP_HTTP_PATH=/mcp`
  - `MCP_HTTP_PUBLISH_PORT=8000` (or another host port)
  - `PUBLIC_BASE_URL=https://cocktail-mcp.example.com`
  - `AUTH_USERNAME=<connector login username>`
  - `AUTH_PASSWORD=<connector login password>`
  - `OAUTH_STORAGE_DIR=/data/oauth`
3. Add a persistent volume for `/data/oauth` so keys, registered clients, and refresh tokens survive redeploys.
4. Use internal service URL for `COCKTAIL_API_BASE_URL` when possible, for example:
   - `http://cocktail-app:3000`
5. Start the cocktail app first, then start the MCP service.
6. In Claude, add a custom connector pointing to `https://<your-fqdn>/mcp`.

### Portainer Error: `.env not found`

If you saw an error like `env file /data/compose/<id>/.env not found`, the stack was expecting a physical `.env` file inside Portainer's compose directory.

This repo now avoids that requirement by reading `COCKTAIL_API_*` from stack environment variables directly.

In Portainer Stack deployment:
- Add these variables in the Stack `Environment variables` UI:
  - `COCKTAIL_API_BASE_URL`
  - `COCKTAIL_API_USERNAME`
  - `COCKTAIL_API_PASSWORD`
  - `PUBLIC_BASE_URL`
  - `AUTH_USERNAME`
  - `AUTH_PASSWORD`
- Redeploy the stack.

Your example values are valid for this setup.

### Portainer Error: `pull access denied for cocktail-recipes-mcp`

This happens when Portainer tries to pull `cocktail-recipes-mcp:latest` from a registry.
This project is intended to build from source in the stack, not pull from Docker Hub.

Resolution:
- Use the current compose file from this repo (it uses `build` and `pull_policy: never`).
- In Portainer stack deployment, disable any "pull latest image" behavior for this stack.
- Redeploy the stack so the image is built locally on the Docker host.

### FQDN vs Internal URL

- If MCP and cocktail app are in the same Docker network, prefer internal URL (`http://service-name:port`).
- If MCP is outside that network, use a reachable external URL/FQDN (for example `https://cocktails.example.com`).

For MCP client access:
- Same LAN/VPN: `http://<host-ip>:<published-port><MCP_HTTP_PATH>`
- Internet-facing: put SWAG/Nginx in front and use `https://<fqdn><MCP_HTTP_PATH>`
### Example Portainer Stack Snippet

```yaml
services:
  cocktail-recipes-mcp:
    image: cocktail-recipes-mcp:latest
    build:
      context: .
      dockerfile: Dockerfile
    environment:
      COCKTAIL_API_BASE_URL: http://cocktail-app:3000
      COCKTAIL_API_USERNAME: admin
      COCKTAIL_API_PASSWORD: change-me
      MCP_TRANSPORT: streamable-http
      MCP_HTTP_HOST: 0.0.0.0
      MCP_HTTP_PORT: 8000
      MCP_HTTP_PATH: /mcp
      PUBLIC_BASE_URL: https://cocktail-mcp.example.com
      AUTH_USERNAME: connector-admin
      AUTH_PASSWORD: change-me
      OAUTH_STORAGE_DIR: /data/oauth
    ports:
      - "8000:8000"
    volumes:
      - oauth_data:/data/oauth
    restart: unless-stopped
    stdin_open: true
    tty: true
    networks:
      - cocktail_net

networks:
  cocktail_net:
    external: true

volumes:
  oauth_data:
```

### Go-Live Checklist

1. MCP and app containers share a network.
2. MCP env vars are set in Portainer, including `PUBLIC_BASE_URL`, `AUTH_USERNAME`, and `AUTH_PASSWORD`.
3. Login endpoint is reachable from MCP (`POST /api/auth/login`).
4. OAuth state volume is mounted.
5. `GET /.well-known/oauth-authorization-server` succeeds.
6. `GET /.well-known/oauth-protected-resource` succeeds.
7. Unauthenticated `GET /mcp` returns `401` with `WWW-Authenticate` pointing at protected-resource metadata.
8. For admin operations, run `dry_run=true` first and apply only with `dry_run=false`.

## Claude Desktop Connection

Add an MCP server entry to your Claude Desktop config.

### Local Python command

```json
{
  "mcpServers": {
    "cocktail-recipes": {
      "command": "/absolute/path/to/cocktail-recipes-mcp/.venv/bin/python",
      "args": ["-m", "cocktail_recipes_mcp.main"],
      "env": {
        "COCKTAIL_API_BASE_URL": "http://localhost:3000",
        "COCKTAIL_API_USERNAME": "admin",
        "COCKTAIL_API_PASSWORD": "change-me"
      }
    }
  }
}
```

### Docker command

```json
{
  "mcpServers": {
    "cocktail-recipes": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "--env-file",
        "/absolute/path/to/cocktail-recipes-mcp/.env",
        "cocktail-recipes-mcp:latest"
      ]
    }
  }
}
```

### Remote HTTP MCP (different machine)

When running in Portainer with `MCP_TRANSPORT=streamable-http`, use your reachable URL:

- Direct host/port example: `http://10.0.30.51:8000/mcp`
- SWAG/FQDN example: `https://mcp.example.com/mcp`

For Claude custom connector setup:

- URL: `https://mcp.example.com/mcp`
- Leave `OAuth Client ID` empty.
- Leave `OAuth Client Secret` empty.
- Claude should dynamically register as a public client and complete OAuth against this server.

Do not put `COCKTAIL_API_USERNAME` or `COCKTAIL_API_PASSWORD` into Claude. Those remain server-side only.

## Tests

Run minimal tests:

```bash
pytest
```

## Manual Verification

Discovery endpoints:

```bash
curl -i https://cocktail-mcp.example.com/.well-known/oauth-authorization-server
curl -i https://cocktail-mcp.example.com/.well-known/oauth-protected-resource
curl -i https://cocktail-mcp.example.com/.well-known/jwks.json
```

Protected MCP endpoint without a token:

```bash
curl -i https://cocktail-mcp.example.com/mcp
```

Expected result:

- `401 Unauthorized`
- `WWW-Authenticate: Bearer ... resource_metadata="https://cocktail-mcp.example.com/.well-known/oauth-protected-resource"`

Automated tests now cover:

- metadata discovery
- dynamic client registration
- authorization code flow with PKCE
- refresh token rotation
- `/mcp` bearer protection

## Example Transcript

See `docs/example_transcripts.md` for a dry_run/apply merge example (`Cucumber` vs `cucumber`).
