from __future__ import annotations

from typing import Any

from .models import ErrorDetails, ToolResult


class ApiError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int | None = None,
        endpoint: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.endpoint = endpoint
        self.details = details or {}

    def to_model(self) -> ErrorDetails:
        return ErrorDetails(
            code=self.code,
            message=self.message,
            status_code=self.status_code,
            endpoint=self.endpoint,
            details=self.details,
        )


def ok_result(data: dict[str, Any] | list[Any]) -> dict[str, Any]:
    return ToolResult(ok=True, data=data).model_dump(mode="json")


def error_result(error: ApiError) -> dict[str, Any]:
    return ToolResult(ok=False, error=error.to_model()).model_dump(mode="json")


def not_implemented_result(action: str, endpoint: str) -> dict[str, Any]:
    return error_result(
        ApiError(
            code="not_implemented",
            message=(
                f"Backend endpoint for '{action}' is not available yet. "
                f"Add/enable endpoint '{endpoint}' in Aephir/cocktail-recipes, then retry."
            ),
            status_code=404,
            endpoint=endpoint,
            details={"action": action},
        )
    )
