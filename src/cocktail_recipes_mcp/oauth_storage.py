from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from mcp.server.auth.provider import AuthorizationCode, RefreshToken
from mcp.shared.auth import OAuthClientInformationFull


class PendingAuthorizationFlow(BaseModel):
    flow_id: str
    client_id: str
    client_name: str | None = None
    redirect_uri: str
    redirect_uri_provided_explicitly: bool
    scopes: list[str]
    state: str | None = None
    code_challenge: str
    resource: str | None = None
    created_at: float
    authenticated_subject: str | None = None


class OAuthStorage:
    def __init__(self, storage_dir: str) -> None:
        self._root = Path(storage_dir)
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._clients_path = self._root / "clients.json"
        self._flows_path = self._root / "flows.json"
        self._codes_path = self._root / "authorization_codes.json"
        self._refresh_tokens_path = self._root / "refresh_tokens.json"

    def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        with self._lock:
            data = self._read_map(self._clients_path)
            payload = data.get(client_id)
            return OAuthClientInformationFull.model_validate(payload) if payload else None

    def save_client(self, client: OAuthClientInformationFull) -> None:
        with self._lock:
            data = self._read_map(self._clients_path)
            data[client.client_id or ""] = client.model_dump(mode="json")
            self._write_map(self._clients_path, data)

    def save_flow(self, flow: PendingAuthorizationFlow) -> None:
        with self._lock:
            data = self._read_map(self._flows_path)
            data[flow.flow_id] = flow.model_dump(mode="json")
            self._write_map(self._flows_path, data)

    def get_flow(self, flow_id: str) -> PendingAuthorizationFlow | None:
        with self._lock:
            data = self._read_map(self._flows_path)
            payload = data.get(flow_id)
            if not payload:
                return None
            flow = PendingAuthorizationFlow.model_validate(payload)
            if flow.created_at + 1800 < time.time():
                data.pop(flow_id, None)
                self._write_map(self._flows_path, data)
                return None
            return flow

    def delete_flow(self, flow_id: str) -> None:
        with self._lock:
            data = self._read_map(self._flows_path)
            data.pop(flow_id, None)
            self._write_map(self._flows_path, data)

    def save_authorization_code(self, auth_code: AuthorizationCode) -> None:
        with self._lock:
            data = self._read_map(self._codes_path)
            data[auth_code.code] = auth_code.model_dump(mode="json")
            self._write_map(self._codes_path, data)

    def get_authorization_code(self, code: str) -> AuthorizationCode | None:
        with self._lock:
            self._cleanup_expired_codes()
            data = self._read_map(self._codes_path)
            payload = data.get(code)
            return AuthorizationCode.model_validate(payload) if payload else None

    def delete_authorization_code(self, code: str) -> None:
        with self._lock:
            data = self._read_map(self._codes_path)
            data.pop(code, None)
            self._write_map(self._codes_path, data)

    def save_refresh_token(self, refresh_token: RefreshToken) -> None:
        with self._lock:
            data = self._read_map(self._refresh_tokens_path)
            data[refresh_token.token] = refresh_token.model_dump(mode="json")
            self._write_map(self._refresh_tokens_path, data)

    def get_refresh_token(self, token: str) -> RefreshToken | None:
        with self._lock:
            self._cleanup_expired_refresh_tokens()
            data = self._read_map(self._refresh_tokens_path)
            payload = data.get(token)
            return RefreshToken.model_validate(payload) if payload else None

    def delete_refresh_token(self, token: str) -> None:
        with self._lock:
            data = self._read_map(self._refresh_tokens_path)
            data.pop(token, None)
            self._write_map(self._refresh_tokens_path, data)

    def _cleanup_expired_codes(self) -> None:
        data = self._read_map(self._codes_path)
        now = time.time()
        filtered = {
            code: payload
            for code, payload in data.items()
            if AuthorizationCode.model_validate(payload).expires_at >= now
        }
        if filtered != data:
            self._write_map(self._codes_path, filtered)

    def _cleanup_expired_refresh_tokens(self) -> None:
        data = self._read_map(self._refresh_tokens_path)
        now = time.time()
        filtered: dict[str, Any] = {}
        for token, payload in data.items():
            refresh = RefreshToken.model_validate(payload)
            if refresh.expires_at is None or refresh.expires_at >= now:
                filtered[token] = payload
        if filtered != data:
            self._write_map(self._refresh_tokens_path, filtered)

    def _read_map(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_map(self, path: Path, payload: dict[str, Any]) -> None:
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        tmp_path.replace(path)
