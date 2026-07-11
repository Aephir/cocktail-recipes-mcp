import base64
import hashlib
from urllib.parse import parse_qs, urlparse

from starlette.testclient import TestClient

from cocktail_recipes_mcp.config import get_settings
from cocktail_recipes_mcp.oauth_app import build_oauth_http_app
from cocktail_recipes_mcp.server import build_server


def _pkce_pair(verifier: str) -> tuple[str, str]:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def _build_client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("COCKTAIL_API_BASE_URL", "http://api.local")
    monkeypatch.setenv("COCKTAIL_API_USERNAME", "admin")
    monkeypatch.setenv("COCKTAIL_API_PASSWORD", "secret")
    monkeypatch.setenv("MCP_TRANSPORT", "streamable-http")
    monkeypatch.setenv("MCP_HTTP_HOST", "0.0.0.0")
    monkeypatch.setenv("MCP_HTTP_PORT", "8000")
    monkeypatch.setenv("MCP_HTTP_PATH", "/mcp")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://cocktail-mcp.aephir.net")
    monkeypatch.setenv("AUTH_USERNAME", "connector-user")
    monkeypatch.setenv("AUTH_PASSWORD", "connector-pass")
    monkeypatch.setenv("OAUTH_STORAGE_DIR", str(tmp_path / "oauth"))
    monkeypatch.setenv("OAUTH_JWT_KEY_PATH", str(tmp_path / "oauth" / "jwt_signing_key.pem"))
    get_settings.cache_clear()
    settings = get_settings()
    server = build_server()
    return TestClient(build_oauth_http_app(server, settings))


def test_metadata_and_unauthorized_mcp(monkeypatch, tmp_path) -> None:
    with _build_client(monkeypatch, tmp_path) as client:
        metadata = client.get("/.well-known/oauth-authorization-server")
        assert metadata.status_code == 200
        payload = metadata.json()
        assert payload["issuer"] == "https://cocktail-mcp.aephir.net"
        assert payload["registration_endpoint"] == "https://cocktail-mcp.aephir.net/register"
        assert payload["token_endpoint_auth_methods_supported"] == ["none"]
        assert payload["jwks_uri"] == "https://cocktail-mcp.aephir.net/.well-known/jwks.json"

        protected_resource = client.get("/.well-known/oauth-protected-resource")
        assert protected_resource.status_code == 200
        assert protected_resource.json()["resource"] == "https://cocktail-mcp.aephir.net/mcp"

        unauthorized = client.get("/mcp")
        assert unauthorized.status_code == 401
        assert 'resource_metadata="https://cocktail-mcp.aephir.net/.well-known/oauth-protected-resource"' in unauthorized.headers[
            "www-authenticate"
        ]


def test_full_authorization_code_flow(monkeypatch, tmp_path) -> None:
    verifier, challenge = _pkce_pair("verifier-value-123")

    with _build_client(monkeypatch, tmp_path) as client:
        registration = client.post(
            "/register",
            json={
                "client_name": "Claude iOS",
                "redirect_uris": ["https://claude.ai/callback"],
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
            },
        )
        assert registration.status_code == 201
        client_id = registration.json()["client_id"]

        authorize = client.get(
            "/authorize",
            params={
                "client_id": client_id,
                "redirect_uri": "https://claude.ai/callback",
                "response_type": "code",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": "abc123",
                "resource": "https://cocktail-mcp.aephir.net/mcp",
            },
            follow_redirects=False,
        )
        assert authorize.status_code == 302
        flow = parse_qs(urlparse(authorize.headers["location"]).query)["flow"][0]

        login = client.post(
            "/oauth/login",
            data={"flow": flow, "username": "connector-user", "password": "connector-pass"},
            follow_redirects=False,
        )
        assert login.status_code == 303

        consent = client.post(
            "/oauth/consent",
            data={"flow": flow, "action": "approve"},
            follow_redirects=False,
        )
        assert consent.status_code == 302
        callback = urlparse(consent.headers["location"])
        query = parse_qs(callback.query)
        code = query["code"][0]
        assert query["state"][0] == "abc123"

        token = client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "https://claude.ai/callback",
                "client_id": client_id,
                "code_verifier": verifier,
                "resource": "https://cocktail-mcp.aephir.net/mcp",
            },
        )
        assert token.status_code == 200
        token_payload = token.json()
        assert token_payload["token_type"] == "Bearer"
        assert token_payload["access_token"]
        assert token_payload["refresh_token"]

        refreshed = client.post(
            "/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": token_payload["refresh_token"],
                "client_id": client_id,
                "scope": "openid profile email",
                "resource": "https://cocktail-mcp.aephir.net/mcp",
            },
        )
        assert refreshed.status_code == 200
        refreshed_payload = refreshed.json()
        assert refreshed_payload["refresh_token"] != token_payload["refresh_token"]

        authorized = client.get("/mcp", headers={"Authorization": f"Bearer {token_payload['access_token']}"})
        assert authorized.status_code != 401


def test_registration_rejects_confidential_clients(monkeypatch, tmp_path) -> None:
    with _build_client(monkeypatch, tmp_path) as client:
        registration = client.post(
            "/register",
            json={
                "client_name": "Invalid confidential client",
                "redirect_uris": ["https://claude.ai/callback"],
                "token_endpoint_auth_method": "client_secret_post",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
            },
        )

        assert registration.status_code == 400
        assert registration.json()["error"] == "invalid_client_metadata"
