from __future__ import annotations

from typing import Any

import httpx

from .config import Settings
from .errors import ApiError


class CocktailApiClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.Client(
            base_url=settings.cocktail_api_base_url.rstrip("/"),
            timeout=httpx.Timeout(settings.cocktail_api_timeout_seconds),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            follow_redirects=True,
        )
        self._authenticated = False

    def close(self) -> None:
        self._client.close()

    def login(self) -> None:
        payload = {
            "username": self._settings.cocktail_api_username,
            "password": self._settings.cocktail_api_password,
        }
        response = self._client.post(self._settings.cocktail_api_login_path, json=payload)

        if response.status_code >= 400:
            raise ApiError(
                code="auth_failed",
                message="Failed to authenticate against cocktail API.",
                status_code=response.status_code,
                endpoint=self._settings.cocktail_api_login_path,
                details={"response": _safe_json(response)},
            )
        self._authenticated = True

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        idempotent: bool = False,
    ) -> dict[str, Any] | list[Any] | None:
        if not self._authenticated:
            self.login()

        attempts = 1 if not idempotent else max(1, self._settings.cocktail_api_max_retries)
        backoff = max(0.0, self._settings.cocktail_api_retry_backoff_seconds)

        last_error: ApiError | None = None

        for attempt in range(1, attempts + 1):
            try:
                response = self._client.request(method, path, params=params, json=json)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = ApiError(
                    code="network_error",
                    message=f"Network error while calling {path}: {exc}",
                    endpoint=path,
                    details={"attempt": attempt},
                )
                if attempt >= attempts:
                    raise last_error
                if backoff > 0:
                    import time

                    time.sleep(backoff * attempt)
                continue

            if response.status_code == 401:
                self.login()
                response = self._client.request(method, path, params=params, json=json)

            if response.status_code == 404:
                raise ApiError(
                    code="not_implemented",
                    message=f"Endpoint not found: {path}",
                    status_code=404,
                    endpoint=path,
                )

            if response.status_code >= 500 and idempotent and attempt < attempts:
                if backoff > 0:
                    import time

                    time.sleep(backoff * attempt)
                continue

            if response.status_code >= 400:
                raise ApiError(
                    code="api_error",
                    message=f"API call failed: {method} {path}",
                    status_code=response.status_code,
                    endpoint=path,
                    details={"response": _safe_json(response)},
                )

            return _safe_json(response)

        if last_error is not None:
            raise last_error
        raise ApiError(code="unknown_error", message="Unexpected API client state", endpoint=path)


def _safe_json(response: httpx.Response) -> dict[str, Any] | list[Any] | None:
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text}
