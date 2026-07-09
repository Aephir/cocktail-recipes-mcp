# cocktail-recipes-mcp

Dockerized Python 3.11 MCP server for the `Aephir/cocktail-recipes` REST API.

This server is designed for Claude Desktop and other MCP clients. It authenticates against the cocktail app via session-cookie login (`POST /api/auth/login`) and uses REST-only calls.

## Features

- Python 3.11 MCP server with typed models and validation
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

Optional variables are in `.env.example`.

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

## Tests

Run minimal tests:

```bash
pytest
```

## Example Transcript

See `docs/example_transcripts.md` for a dry_run/apply merge example (`Cucumber` vs `cucumber`).
