from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Any, cast

from pydantic import AnyHttpUrl, TypeAdapter, ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from mcp.server.auth.errors import stringify_pydantic_error
from mcp.server.auth.handlers.authorize import AuthorizationHandler
from mcp.server.auth.handlers.token import TokenHandler
from mcp.server.auth.json_response import PydanticJSONResponse
from mcp.server.auth.middleware.client_auth import ClientAuthenticator
from mcp.server.auth.provider import AuthorizationCode, construct_redirect_uri
from mcp.server.auth.settings import ClientRegistrationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata

from .config import Settings
from .oauth_provider import DEFAULT_SCOPES, EmbeddedOAuthProvider
from .oauth_storage import OAuthStorage
from .oauth_tokens import JWTSignerVerifier

HTTP_URL = TypeAdapter(AnyHttpUrl)


class OAuthProtectedMCPApp:
    def __init__(self, app: ASGIApp, verifier: JWTSignerVerifier, *, issuer: str, audience: str, resource_metadata_url: str):
        self.app = app
        self.verifier = verifier
        self.issuer = issuer
        self.audience = audience
        self.resource_metadata_url = resource_metadata_url

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1") for key, value in scope.get("headers", [])
        }
        auth_header = headers.get("authorization", "")
        token = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else None
        verified = self.verifier.verify_access_token(token, issuer=self.issuer, audience=self.audience) if token else None

        if not verified:
            body = {"error": "invalid_token", "error_description": "Valid bearer token required"}
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (
                            b"www-authenticate",
                            f'Bearer error="invalid_token", error_description="Valid bearer token required", resource_metadata="{self.resource_metadata_url}"'.encode(),
                        ),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": JSONResponse(body).body})
            return

        await self.app(scope, receive, send)


@dataclass
class RegistrationHandler:
    provider: EmbeddedOAuthProvider
    options: ClientRegistrationOptions

    async def handle(self, request: Request) -> Response:
        try:
            body = await request.json()
            client_metadata = OAuthClientMetadata.model_validate(body)
        except ValidationError as validation_error:
            return JSONResponse(
                {
                    "error": "invalid_client_metadata",
                    "error_description": stringify_pydantic_error(validation_error),
                },
                status_code=400,
            )

        if client_metadata.token_endpoint_auth_method is None:
            client_metadata.token_endpoint_auth_method = "none"

        if client_metadata.token_endpoint_auth_method != "none":
            return JSONResponse(
                {
                    "error": "invalid_client_metadata",
                    "error_description": "Only public clients with token_endpoint_auth_method=none are supported",
                },
                status_code=400,
            )

        if client_metadata.scope is None and self.options.default_scopes is not None:
            client_metadata.scope = " ".join(self.options.default_scopes)

        client_info = OAuthClientInformationFull(
            client_id=secrets.token_urlsafe(24),
            client_secret=None,
            client_id_issued_at=int(time.time()),
            client_secret_expires_at=None,
            redirect_uris=client_metadata.redirect_uris,
            token_endpoint_auth_method=client_metadata.token_endpoint_auth_method,
            grant_types=client_metadata.grant_types,
            response_types=client_metadata.response_types,
            scope=client_metadata.scope,
            client_name=client_metadata.client_name,
            client_uri=client_metadata.client_uri,
            logo_uri=client_metadata.logo_uri,
            contacts=client_metadata.contacts,
            tos_uri=client_metadata.tos_uri,
            policy_uri=client_metadata.policy_uri,
            jwks_uri=client_metadata.jwks_uri,
            jwks=client_metadata.jwks,
            software_id=client_metadata.software_id,
            software_version=client_metadata.software_version,
        )
        await self.provider.register_client(client_info)
        return PydanticJSONResponse(client_info, status_code=201)


@dataclass
class OAuthUIHandlers:
    settings: Settings
    storage: OAuthStorage
    provider: EmbeddedOAuthProvider
    signer: JWTSignerVerifier

    async def authorization_server_metadata(self, request: Request) -> Response:
        issuer = self.provider.issuer_url
        return JSONResponse(
            {
                "issuer": issuer,
                "authorization_endpoint": f"{issuer}/authorize",
                "token_endpoint": f"{issuer}/token",
                "registration_endpoint": f"{issuer}/register",
                "jwks_uri": f"{issuer}/.well-known/jwks.json",
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "refresh_token"],
                "token_endpoint_auth_methods_supported": ["none"],
                "code_challenge_methods_supported": ["S256"],
                "scopes_supported": DEFAULT_SCOPES,
            }
        )

    async def protected_resource_metadata(self, request: Request) -> Response:
        return JSONResponse(
            {
                "resource": self.provider.public_mcp_url,
                "authorization_servers": [self.provider.issuer_url],
                "bearer_methods_supported": ["header"],
                "scopes_supported": DEFAULT_SCOPES,
            }
        )

    async def jwks(self, request: Request) -> Response:
        return JSONResponse(self.signer.jwks())

    async def login(self, request: Request) -> Response:
        flow_id = request.query_params.get("flow") if request.method == "GET" else None
        if request.method == "POST":
            form = await request.form()
            flow_id = str(form.get("flow", ""))
            username = str(form.get("username", ""))
            password = str(form.get("password", ""))
            flow = self.storage.get_flow(flow_id)
            if not flow:
                return HTMLResponse("Invalid or expired login flow", status_code=400)
            if username != self.settings.auth_username or password != self.settings.auth_password:
                return self._login_page(flow_id, error="Invalid credentials", status_code=401)
            flow.authenticated_subject = username
            self.storage.save_flow(flow)
            return RedirectResponse(f"/oauth/consent?flow={flow_id}", status_code=303)

        if not flow_id:
            return HTMLResponse("Missing flow identifier", status_code=400)
        flow = self.storage.get_flow(flow_id)
        if not flow:
            return HTMLResponse("Invalid or expired login flow", status_code=400)
        return self._login_page(flow_id)

    async def consent(self, request: Request) -> Response:
        flow_id = request.query_params.get("flow") if request.method == "GET" else None
        if request.method == "POST":
            form = await request.form()
            flow_id = str(form.get("flow", ""))
            action = str(form.get("action", "deny"))
            flow = self.storage.get_flow(flow_id)
            if not flow or not flow.authenticated_subject:
                return HTMLResponse("Invalid or expired consent flow", status_code=400)

            if action != "approve":
                self.storage.delete_flow(flow_id)
                return RedirectResponse(
                    construct_redirect_uri(flow.redirect_uri, error="access_denied", state=flow.state),
                    status_code=302,
                )

            code = AuthorizationCode(
                code=secrets.token_urlsafe(32),
                scopes=flow.scopes,
                expires_at=time.time() + self.settings.oauth_authorization_code_ttl_seconds,
                client_id=flow.client_id,
                code_challenge=flow.code_challenge,
                redirect_uri=HTTP_URL.validate_python(flow.redirect_uri),
                redirect_uri_provided_explicitly=flow.redirect_uri_provided_explicitly,
                resource=flow.resource,
                subject=flow.authenticated_subject,
            )
            self.storage.save_authorization_code(code)
            self.storage.delete_flow(flow_id)
            return RedirectResponse(
                construct_redirect_uri(flow.redirect_uri, code=code.code, state=flow.state),
                status_code=302,
            )

        if not flow_id:
            return HTMLResponse("Missing flow identifier", status_code=400)
        flow = self.storage.get_flow(flow_id)
        if not flow or not flow.authenticated_subject:
            return HTMLResponse("Invalid or expired consent flow", status_code=400)
        return self._consent_page(flow)

    def _login_page(self, flow_id: str, *, error: str | None = None, status_code: int = 200) -> HTMLResponse:
        error_html = f'<p style="color:#b00020;">{error}</p>' if error else ""
        return HTMLResponse(
            f"""
            <html><body>
            <h1>Sign in to cocktail-recipes-mcp</h1>
            {error_html}
            <form method=\"post\" action=\"/oauth/login\">
              <input type=\"hidden\" name=\"flow\" value=\"{flow_id}\" />
              <label>Username <input type=\"text\" name=\"username\" /></label><br/>
              <label>Password <input type=\"password\" name=\"password\" /></label><br/>
              <button type=\"submit\">Sign in</button>
            </form>
            </body></html>
            """,
            status_code=status_code,
        )

    def _consent_page(self, flow: Any) -> HTMLResponse:
        scopes = " ".join(flow.scopes)
        client_name = flow.client_name or flow.client_id
        return HTMLResponse(
            f"""
            <html><body>
            <h1>Authorize access</h1>
            <p><strong>{client_name}</strong> wants access to your MCP server.</p>
            <p>Scopes: {scopes}</p>
            <p>Resource: {flow.resource}</p>
            <form method=\"post\" action=\"/oauth/consent\">
              <input type=\"hidden\" name=\"flow\" value=\"{flow.flow_id}\" />
              <button type=\"submit\" name=\"action\" value=\"approve\">Allow</button>
              <button type=\"submit\" name=\"action\" value=\"deny\">Deny</button>
            </form>
            </body></html>
            """
        )


def build_oauth_http_app(server: Any, settings: Settings) -> Starlette:
    storage = OAuthStorage(settings.oauth_storage_dir)
    signer = JWTSignerVerifier(settings.oauth_jwt_key_path)
    provider = EmbeddedOAuthProvider(settings=settings, storage=storage, signer=signer)
    issuer_url = HTTP_URL.validate_python(cast(str, settings.public_base_url))
    client_registration_options = ClientRegistrationOptions(enabled=True, valid_scopes=DEFAULT_SCOPES, default_scopes=DEFAULT_SCOPES)
    ui = OAuthUIHandlers(settings=settings, storage=storage, provider=provider, signer=signer)

    mcp_app = server.streamable_http_app()
    protected_mcp = OAuthProtectedMCPApp(
        mcp_app,
        signer,
        issuer=provider.issuer_url,
        audience=provider.public_mcp_url,
        resource_metadata_url=provider.resource_metadata_url,
    )

    authorize_handler = AuthorizationHandler(provider)
    token_handler = TokenHandler(provider, ClientAuthenticator(provider))
    register_handler = RegistrationHandler(provider, client_registration_options)

    routes = [
        Route("/.well-known/oauth-authorization-server", endpoint=ui.authorization_server_metadata, methods=["GET"]),
        Route("/.well-known/oauth-protected-resource", endpoint=ui.protected_resource_metadata, methods=["GET"]),
        Route("/.well-known/jwks.json", endpoint=ui.jwks, methods=["GET"]),
        Route("/authorize", endpoint=authorize_handler.handle, methods=["GET", "POST"]),
        Route("/token", endpoint=token_handler.handle, methods=["POST"]),
        Route("/register", endpoint=register_handler.handle, methods=["POST"]),
        Route("/oauth/login", endpoint=ui.login, methods=["GET", "POST"]),
        Route("/oauth/consent", endpoint=ui.consent, methods=["GET", "POST"]),
        Route(settings.mcp_http_path, endpoint=protected_mcp),
    ]

    return Starlette(debug=False, routes=routes, lifespan=lambda app: server.session_manager.run())
