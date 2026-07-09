from __future__ import annotations

from typing import Any

from .client import CocktailApiClient
from .errors import ApiError
from .models import BulkTagsRequest, MergeRequest, RecategorizeRequest


class CocktailService:
    def __init__(self, client: CocktailApiClient) -> None:
        self._client = client

    def list_recipes(self, limit: int = 100, offset: int = 0) -> dict[str, Any] | list[Any] | None:
        return self._client.request(
            "GET",
            "/api/recipes",
            params={"limit": limit, "offset": offset},
            idempotent=True,
        )

    def get_recipe(self, recipe_id: int) -> dict[str, Any] | list[Any] | None:
        return self._client.request("GET", f"/api/recipes/{recipe_id}", idempotent=True)

    def create_recipe(self, payload: dict[str, Any], dry_run: bool = True) -> dict[str, Any]:
        preview = {
            "operation": "create_recipe",
            "dry_run": dry_run,
            "affected": {"count": 1},
            "payload_preview": payload,
        }
        if dry_run:
            return {"preview": preview, "apply_executed": False}

        result = self._client.request("POST", "/api/recipes", json=payload, idempotent=False)
        return {
            "preview": preview,
            "apply_executed": True,
            "result": result,
        }

    def update_recipe(self, recipe_id: int, payload: dict[str, Any], dry_run: bool = True) -> dict[str, Any]:
        preview = {
            "operation": "update_recipe",
            "dry_run": dry_run,
            "affected": {"recipe_ids": [recipe_id], "count": 1},
            "payload_preview": payload,
        }
        if dry_run:
            return {"preview": preview, "apply_executed": False}

        result = self._client.request("PUT", f"/api/recipes/{recipe_id}", json=payload, idempotent=False)
        return {
            "preview": preview,
            "apply_executed": True,
            "result": result,
        }

    def delete_recipe(self, recipe_id: int, dry_run: bool = True) -> dict[str, Any]:
        preview = {
            "operation": "delete_recipe",
            "dry_run": dry_run,
            "affected": {"recipe_ids": [recipe_id], "count": 1},
        }
        if dry_run:
            return {"preview": preview, "apply_executed": False}

        result = self._client.request("DELETE", f"/api/recipes/{recipe_id}", idempotent=False)
        return {
            "preview": preview,
            "apply_executed": True,
            "result": result,
        }

    def list_ingredients(self, limit: int = 250, offset: int = 0) -> dict[str, Any] | list[Any] | None:
        return self._client.request(
            "GET",
            "/api/ingredients",
            params={"limit": limit, "offset": offset},
            idempotent=True,
        )

    def list_tools(self, limit: int = 250, offset: int = 0) -> dict[str, Any] | list[Any] | None:
        return self._client.request(
            "GET",
            "/api/tools",
            params={"limit": limit, "offset": offset},
            idempotent=True,
        )

    def merge_ingredients(self, req: MergeRequest) -> dict[str, Any] | list[Any] | None:
        payload = req.model_dump(mode="json")
        return self._client.request(
            "POST",
            "/api/admin/ingredients/merge",
            json=payload,
            idempotent=req.dry_run,
        )

    def merge_tools(self, req: MergeRequest) -> dict[str, Any] | list[Any] | None:
        payload = req.model_dump(mode="json")
        return self._client.request(
            "POST",
            "/api/admin/tools/merge",
            json=payload,
            idempotent=req.dry_run,
        )

    def recategorize_recipes(self, req: RecategorizeRequest) -> dict[str, Any] | list[Any] | None:
        payload = req.model_dump(mode="json")
        return self._client.request(
            "POST",
            "/api/admin/recipes/recategorize",
            json=payload,
            idempotent=req.dry_run,
        )

    def update_tags_bulk(self, req: BulkTagsRequest) -> dict[str, Any] | list[Any] | None:
        payload = req.model_dump(mode="json")
        return self._client.request(
            "POST",
            "/api/admin/recipes/tags/bulk",
            json=payload,
            idempotent=req.dry_run,
        )

    def api_capabilities(self) -> list[dict[str, Any]]:
        checks = [
            ("list_recipes", "OPTIONS", "/api/recipes"),
            ("get_recipe", "OPTIONS", "/api/recipes/{id}"),
            ("create_recipe", "OPTIONS", "/api/recipes"),
            ("update_recipe", "OPTIONS", "/api/recipes/{id}"),
            ("delete_recipe", "OPTIONS", "/api/recipes/{id}"),
            ("list_ingredients", "OPTIONS", "/api/ingredients"),
            ("list_tools", "OPTIONS", "/api/tools"),
            ("merge_ingredients", "OPTIONS", "/api/admin/ingredients/merge"),
            ("merge_tools", "OPTIONS", "/api/admin/tools/merge"),
            ("recategorize_recipes", "OPTIONS", "/api/admin/recipes/recategorize"),
            ("update_tags_bulk", "OPTIONS", "/api/admin/recipes/tags/bulk"),
        ]
        out: list[dict[str, Any]] = []
        for action, method, path in checks:
            probe_path = path.replace("{id}", "1")
            supported = True
            note = ""
            try:
                self._client.request(method, probe_path, idempotent=True)
            except ApiError as exc:
                if exc.status_code == 404:
                    supported = False
                    note = "Endpoint is missing in backend app"
                elif exc.status_code == 405:
                    supported = True
                    note = "OPTIONS not allowed, endpoint likely present"
                else:
                    supported = False
                    note = f"Probe failed: {exc.message}"
            out.append(
                {
                    "action": action,
                    "method": method,
                    "path": path,
                    "supported": supported,
                    "note": note,
                }
            )
        return out
