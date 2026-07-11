from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import cast
from urllib.parse import quote

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    RegistrationError,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from .config import Settings
from .oauth_storage import OAuthStorage, PendingAuthorizationFlow
from .oauth_tokens import JWTSignerVerifier

DEFAULT_SCOPES = ["openid", "profile", "email"]


@dataclass
class EmbeddedOAuthProvider(
    OAuthAuthorizationServerProvider[
        AuthorizationCode,
        RefreshToken,
        AccessToken,
    ]
):
    settings: Settings
    storage: OAuthStorage
    signer: JWTSignerVerifier

    @property
    def issuer_url(self) -> str:
        return cast(str, self.settings.public_base_url).rstrip("/")

    @property
    def public_mcp_url(self) -> str:
        return f"{self.issuer_url}{self.settings.mcp_http_path}"

    @property
    def resource_metadata_url(self) -> str:
        return f"{self.issuer_url}/.well-known/oauth-protected-resource"

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self.storage.get_client(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        allowlist = self._redirect_allowlist()
        redirect_uris = client_info.redirect_uris or []
        if allowlist:
            for redirect_uri in redirect_uris:
                redirect = str(redirect_uri)
                if not any(redirect.startswith(prefix) for prefix in allowlist):
                    raise RegistrationError(
                        error="invalid_redirect_uri",
                        error_description=f"Redirect URI not allowed: {redirect}",
                    )
        self.storage.save_client(client_info)

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        flow_id = secrets.token_urlsafe(24)
        scopes = params.scopes or (client.scope.split() if client.scope else DEFAULT_SCOPES)
        flow = PendingAuthorizationFlow(
            flow_id=flow_id,
            client_id=client.client_id or "",
            client_name=client.client_name,
            redirect_uri=str(params.redirect_uri),
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            scopes=scopes,
            state=params.state,
            code_challenge=params.code_challenge,
            resource=params.resource or self.public_mcp_url,
            created_at=time.time(),
        )
        self.storage.save_flow(flow)
        return f"{self.issuer_url}/oauth/login?flow={quote(flow_id)}"

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        return self.storage.get_authorization_code(authorization_code)

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        self.storage.delete_authorization_code(authorization_code.code)
        refresh = self._issue_refresh_token(
            client_id=client.client_id or "",
            scopes=authorization_code.scopes,
            subject=authorization_code.subject or self.settings.auth_username or "mcp-user",
        )
        access_token, _expires_at = self.signer.sign_access_token(
            issuer=self.issuer_url,
            audience=authorization_code.resource or self.public_mcp_url,
            client_id=client.client_id or "",
            scopes=authorization_code.scopes,
            subject=authorization_code.subject or self.settings.auth_username or "mcp-user",
            ttl_seconds=self.settings.oauth_access_token_ttl_seconds,
        )
        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=self.settings.oauth_access_token_ttl_seconds,
            refresh_token=refresh.token,
            scope=" ".join(authorization_code.scopes),
        )

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        return self.storage.get_refresh_token(refresh_token)

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        self.storage.delete_refresh_token(refresh_token.token)
        rotated = self._issue_refresh_token(
            client_id=client.client_id or "",
            scopes=scopes,
            subject=refresh_token.subject or self.settings.auth_username or "mcp-user",
        )
        access_token, _expires_at = self.signer.sign_access_token(
            issuer=self.issuer_url,
            audience=self.public_mcp_url,
            client_id=client.client_id or "",
            scopes=scopes,
            subject=refresh_token.subject or self.settings.auth_username or "mcp-user",
            ttl_seconds=self.settings.oauth_access_token_ttl_seconds,
        )
        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=self.settings.oauth_access_token_ttl_seconds,
            refresh_token=rotated.token,
            scope=" ".join(scopes),
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        return self.signer.verify_access_token(token, issuer=self.issuer_url, audience=self.public_mcp_url)

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        if isinstance(token, RefreshToken):
            self.storage.delete_refresh_token(token.token)

    def _issue_refresh_token(self, *, client_id: str, scopes: list[str], subject: str) -> RefreshToken:
        token = RefreshToken(
            token=secrets.token_urlsafe(32),
            client_id=client_id,
            scopes=scopes,
            expires_at=int(time.time()) + self.settings.oauth_refresh_token_ttl_seconds,
            subject=subject,
        )
        self.storage.save_refresh_token(token)
        return token

    def _redirect_allowlist(self) -> list[str]:
        raw = self.settings.oauth_client_redirect_allowlist
        if not raw:
            return []
        return [item.strip() for item in raw.split(",") if item.strip()]
