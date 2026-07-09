import httpx
import respx

from cocktail_recipes_mcp.client import CocktailApiClient
from cocktail_recipes_mcp.config import Settings


def _settings() -> Settings:
    return Settings(
        COCKTAIL_API_BASE_URL="http://api.local",
        COCKTAIL_API_USERNAME="user",
        COCKTAIL_API_PASSWORD="pass",
        COCKTAIL_API_LOGIN_PATH="/api/auth/login",
        COCKTAIL_API_TIMEOUT_SECONDS=5,
        COCKTAIL_API_MAX_RETRIES=2,
        COCKTAIL_API_RETRY_BACKOFF_SECONDS=0,
    )


@respx.mock
def test_relogin_on_401() -> None:
    settings = _settings()
    client = CocktailApiClient(settings)

    login_route = respx.post("http://api.local/api/auth/login").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    recipes_route = respx.get("http://api.local/api/recipes").mock(
        side_effect=[
            httpx.Response(401, json={"error": "expired"}),
            httpx.Response(200, json={"items": []}),
        ]
    )

    result = client.request("GET", "/api/recipes", idempotent=True)

    assert result == {"items": []}
    assert login_route.call_count == 2
    assert recipes_route.call_count == 2

    client.close()
