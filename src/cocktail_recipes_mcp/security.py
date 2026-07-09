from __future__ import annotations

import base64
import binascii
import hmac
from typing import Any


def is_authorized_header(
    authorization_header: str | None,
    *,
    bearer_token: str | None = None,
    basic_username: str | None = None,
    basic_password: str | None = None,
) -> bool:
    if not bearer_token and not (basic_username and basic_password):
        return True

    if not authorization_header:
        return False

    header = authorization_header.strip()

    if bearer_token and header.lower().startswith("bearer "):
        token = header[7:].strip()
        return hmac.compare_digest(token, bearer_token)

    if basic_username and basic_password and header.lower().startswith("basic "):
        encoded = header[6:].strip()
        try:
            decoded = base64.b64decode(encoded).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            return False

        if ":" not in decoded:
            return False

        username, password = decoded.split(":", 1)
        return hmac.compare_digest(username, basic_username) and hmac.compare_digest(password, basic_password)

    return False


class MCPHTTPAuthMiddleware:
    def __init__(
        self,
        app: Any,
        *,
        path_prefix: str,
        bearer_token: str | None = None,
        basic_username: str | None = None,
        basic_password: str | None = None,
    ) -> None:
        self.app = app
        self.path_prefix = path_prefix
        self.bearer_token = bearer_token
        self.basic_username = basic_username
        self.basic_password = basic_password

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not path.startswith(self.path_prefix):
            await self.app(scope, receive, send)
            return

        headers: dict[str, str] = {
            key.decode("latin-1").lower(): value.decode("latin-1") for key, value in scope.get("headers", [])
        }

        allowed = is_authorized_header(
            headers.get("authorization"),
            bearer_token=self.bearer_token,
            basic_username=self.basic_username,
            basic_password=self.basic_password,
        )

        if allowed:
            await self.app(scope, receive, send)
            return

        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"www-authenticate", b"Bearer, Basic realm=\"cocktail-recipes-mcp\""),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b'{"error":"unauthorized","message":"Valid Authorization header required"}',
            }
        )
