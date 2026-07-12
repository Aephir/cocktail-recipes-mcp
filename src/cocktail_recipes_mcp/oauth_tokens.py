from __future__ import annotations

import base64
import hashlib
import secrets
import time
from pathlib import Path
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import InvalidTokenError

from mcp.server.auth.provider import AccessToken


def _b64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


class JWTSignerVerifier:
    def __init__(self, key_path: str) -> None:
        self._key_path = Path(key_path)
        self._key_path.parent.mkdir(parents=True, exist_ok=True)
        self._private_key = self._load_or_create_private_key()
        self._public_key = self._private_key.public_key()
        der = self._public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        self.kid = hashlib.sha256(der).hexdigest()[:16]

    def sign_access_token(
        self,
        *,
        issuer: str,
        audience: str,
        client_id: str,
        scopes: list[str],
        subject: str,
        ttl_seconds: int,
    ) -> tuple[str, int]:
        now = int(time.time())
        expires_at = now + ttl_seconds
        payload = {
            "iss": issuer,
            "aud": audience,
            "sub": subject,
            "client_id": client_id,
            "scope": " ".join(scopes),
            "iat": now,
            "nbf": now,
            "exp": expires_at,
            "jti": secrets.token_urlsafe(24),
        }
        token = jwt.encode(payload, self._private_key, algorithm="RS256", headers={"kid": self.kid})
        return token, expires_at

    def verify_access_token(self, token: str, *, issuer: str, audience: str) -> AccessToken | None:
        try:
            claims = jwt.decode(token, self._public_key, algorithms=["RS256"], issuer=issuer, audience=audience)
        except InvalidTokenError:
            return None

        scopes = str(claims.get("scope", "")).split()
        return AccessToken(
            token=token,
            client_id=str(claims.get("client_id", "")),
            scopes=scopes,
            expires_at=int(claims["exp"]),
            resource=str(claims.get("aud", audience)),
            subject=str(claims.get("sub", "")),
            claims=claims,
        )

    def jwks(self) -> dict[str, Any]:
        public_numbers = self._public_key.public_numbers()
        return {
            "keys": [
                {
                    "kty": "RSA",
                    "alg": "RS256",
                    "use": "sig",
                    "kid": self.kid,
                    "n": _b64url_uint(public_numbers.n),
                    "e": _b64url_uint(public_numbers.e),
                }
            ]
        }

    def _load_or_create_private_key(self) -> rsa.RSAPrivateKey:
        if self._key_path.exists():
            return serialization.load_pem_private_key(self._key_path.read_bytes(), password=None)

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        self._key_path.write_bytes(pem)
        return private_key
