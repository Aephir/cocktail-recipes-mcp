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

        # Preserve omitted mutable fields (for example tools/garnishes) by fetching
        # the current recipe and merging caller updates over a normalized payload.
        current_recipe = self.get_recipe(recipe_id)
        update_payload = _merge_recipe_update_payload(current_recipe=current_recipe, incoming=payload)
        result = self._client.request("PUT", f"/api/recipes/{recipe_id}", json=update_payload, idempotent=False)
        _assert_apply_executed(operation="update_recipe", dry_run=dry_run, result=result)
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
        _assert_apply_executed(operation="delete_recipe", dry_run=dry_run, result=result)
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

    def create_ingredient(self, name: str, dry_run: bool = True) -> dict[str, Any]:
        payload = {"name": name}
        preview = {
            "operation": "create_ingredient",
            "dry_run": dry_run,
            "affected": {"count": 1},
            "payload_preview": payload,
        }
        if dry_run:
            return {"preview": preview, "apply_executed": False}

        result = self._client.request("POST", "/api/admin/ingredients", json=payload, idempotent=False)
        _assert_apply_executed(operation="create_ingredient", dry_run=dry_run, result=result)
        return {
            "preview": preview,
            "apply_executed": True,
            "result": result,
        }

    def update_ingredient(self, ingredient_id: int, name: str, dry_run: bool = True) -> dict[str, Any]:
        payload = {"name": name}
        preview = {
            "operation": "update_ingredient",
            "dry_run": dry_run,
            "affected": {"ingredient_ids": [ingredient_id], "count": 1},
            "payload_preview": payload,
        }
        if dry_run:
            return {"preview": preview, "apply_executed": False}

        result = self._client.request(
            "PUT",
            f"/api/admin/ingredients/{ingredient_id}",
            json=payload,
            idempotent=False,
        )
        _assert_apply_executed(operation="update_ingredient", dry_run=dry_run, result=result)
        return {
            "preview": preview,
            "apply_executed": True,
            "result": result,
        }

    def delete_ingredient(self, ingredient_id: int, dry_run: bool = True, force: bool = False) -> dict[str, Any]:
        refs = self.find_ingredient_references(ingredient_id=ingredient_id)
        warning = None
        if refs["reference_count"] > 0:
            warning = {
                "code": "in_use",
                "message": "Ingredient appears in recipe references.",
                "details": refs,
            }

        preview = {
            "operation": "delete_ingredient",
            "dry_run": dry_run,
            "force": force,
            "affected": {"ingredient_ids": [ingredient_id], "count": 1},
            "warning": warning,
        }
        if dry_run:
            return {"preview": preview, "apply_executed": False}

        if warning and not force:
            return {
                "preview": preview,
                "apply_executed": False,
                "blocked": True,
                "reason": "Ingredient is referenced by recipes. Re-run with force=true only after review.",
            }

        # Send flags in both params and JSON to accommodate backends that only
        # read one transport style for DELETE payloads.
        apply_flags = {"dry_run": False, "force": force}
        result = self._client.request(
            "DELETE",
            f"/api/admin/ingredients/{ingredient_id}",
            params=apply_flags,
            json=apply_flags,
            idempotent=False,
        )
        _assert_apply_executed(operation="delete_ingredient", dry_run=dry_run, result=result)
        return {
            "preview": preview,
            "apply_executed": True,
            "result": result,
        }

    def create_tool(self, name: str, dry_run: bool = True) -> dict[str, Any]:
        payload = {"name": name}
        preview = {
            "operation": "create_tool",
            "dry_run": dry_run,
            "affected": {"count": 1},
            "payload_preview": payload,
        }
        if dry_run:
            return {"preview": preview, "apply_executed": False}

        result = self._client.request("POST", "/api/admin/tools", json=payload, idempotent=False)
        _assert_apply_executed(operation="create_tool", dry_run=dry_run, result=result)
        return {
            "preview": preview,
            "apply_executed": True,
            "result": result,
        }

    def update_tool(self, tool_id: int, name: str, dry_run: bool = True) -> dict[str, Any]:
        payload = {"name": name}
        preview = {
            "operation": "update_tool",
            "dry_run": dry_run,
            "affected": {"tool_ids": [tool_id], "count": 1},
            "payload_preview": payload,
        }
        if dry_run:
            return {"preview": preview, "apply_executed": False}

        result = self._client.request("PUT", f"/api/admin/tools/{tool_id}", json=payload, idempotent=False)
        _assert_apply_executed(operation="update_tool", dry_run=dry_run, result=result)
        return {
            "preview": preview,
            "apply_executed": True,
            "result": result,
        }

    def delete_tool(self, tool_id: int, dry_run: bool = True, force: bool = False) -> dict[str, Any]:
        refs = self.find_tool_references(tool_id=tool_id)
        warning = None
        if refs["reference_count"] > 0:
            warning = {
                "code": "in_use",
                "message": "Tool appears in recipe references.",
                "details": refs,
            }

        preview = {
            "operation": "delete_tool",
            "dry_run": dry_run,
            "force": force,
            "affected": {"tool_ids": [tool_id], "count": 1},
            "warning": warning,
        }
        if dry_run:
            return {"preview": preview, "apply_executed": False}

        if warning and not force:
            return {
                "preview": preview,
                "apply_executed": False,
                "blocked": True,
                "reason": "Tool is referenced by recipes. Re-run with force=true only after review.",
            }

        # Send flags in both params and JSON to accommodate backends that only
        # read one transport style for DELETE payloads.
        apply_flags = {"dry_run": False, "force": force}
        result = self._client.request(
            "DELETE",
            f"/api/admin/tools/{tool_id}",
            params=apply_flags,
            json=apply_flags,
            idempotent=False,
        )
        _assert_apply_executed(operation="delete_tool", dry_run=dry_run, result=result)
        return {
            "preview": preview,
            "apply_executed": True,
            "result": result,
        }

    def merge_ingredients(self, req: MergeRequest) -> dict[str, Any] | list[Any] | None:
        payload = req.model_dump(mode="json")
        result = self._client.request(
            "POST",
            "/api/admin/ingredients/merge",
            json=payload,
            idempotent=req.dry_run,
        )
        _assert_apply_executed(operation="merge_ingredients", dry_run=req.dry_run, result=result)
        return result

    def merge_tools(self, req: MergeRequest) -> dict[str, Any] | list[Any] | None:
        payload = req.model_dump(mode="json")
        result = self._client.request(
            "POST",
            "/api/admin/tools/merge",
            json=payload,
            idempotent=req.dry_run,
        )
        _assert_apply_executed(operation="merge_tools", dry_run=req.dry_run, result=result)
        return result

    def recategorize_recipes(self, req: RecategorizeRequest) -> dict[str, Any] | list[Any] | None:
        payload = req.model_dump(mode="json")
        result = self._client.request(
            "POST",
            "/api/admin/recipes/recategorize",
            json=payload,
            idempotent=req.dry_run,
        )
        _assert_apply_executed(operation="recategorize_recipes", dry_run=req.dry_run, result=result)
        return result

    def bulk_update_recipes(
        self,
        filters: dict[str, Any],
        updates: dict[str, Any],
        dry_run: bool = True,
    ) -> dict[str, Any] | list[Any] | None:
        payload = {
            "dry_run": dry_run,
            "filters": filters,
            "updates": updates,
        }
        preview = {
            "operation": "bulk_update_recipes",
            "dry_run": dry_run,
            "filters": filters,
            "updates": updates,
        }
        if dry_run:
            result = self._client.request(
                "POST",
                "/api/admin/recipes/bulk-update",
                json=payload,
                idempotent=True,
            )
            return {
                "preview": preview,
                "apply_executed": False,
                "result": result,
            }

        result = self._client.request(
            "POST",
            "/api/admin/recipes/bulk-update",
            json=payload,
            idempotent=False,
        )
        _assert_apply_executed(operation="bulk_update_recipes", dry_run=dry_run, result=result)
        return {
            "preview": preview,
            "apply_executed": True,
            "result": result,
        }

    def update_tags_bulk(self, req: BulkTagsRequest) -> dict[str, Any] | list[Any] | None:
        payload = req.model_dump(mode="json")
        result = self._client.request(
            "POST",
            "/api/admin/recipes/tags/bulk",
            json=payload,
            idempotent=req.dry_run,
        )
        _assert_apply_executed(operation="update_tags_bulk", dry_run=req.dry_run, result=result)
        return result

    def api_capabilities(self) -> list[dict[str, Any]]:
        checks = [
            ("list_recipes", "OPTIONS", "/api/recipes"),
            ("get_recipe", "OPTIONS", "/api/recipes/{id}"),
            ("create_recipe", "OPTIONS", "/api/recipes"),
            ("update_recipe", "OPTIONS", "/api/recipes/{id}"),
            ("delete_recipe", "OPTIONS", "/api/recipes/{id}"),
            ("list_ingredients", "OPTIONS", "/api/ingredients"),
            ("create_ingredient", "OPTIONS", "/api/admin/ingredients"),
            ("update_ingredient", "OPTIONS", "/api/admin/ingredients/{id}"),
            ("delete_ingredient", "OPTIONS", "/api/admin/ingredients/{id}"),
            ("list_tools", "OPTIONS", "/api/tools"),
            ("create_tool", "OPTIONS", "/api/admin/tools"),
            ("update_tool", "OPTIONS", "/api/admin/tools/{id}"),
            ("delete_tool", "OPTIONS", "/api/admin/tools/{id}"),
            ("merge_ingredients", "OPTIONS", "/api/admin/ingredients/merge"),
            ("merge_tools", "OPTIONS", "/api/admin/tools/merge"),
            ("recategorize_recipes", "OPTIONS", "/api/admin/recipes/recategorize"),
            ("bulk_update_recipes", "OPTIONS", "/api/admin/recipes/bulk-update"),
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

    def find_ingredient_references(self, ingredient_id: int, max_scan: int = 2000) -> dict[str, Any]:
        return self._find_recipe_references(entity_key="ingredient_id", entity_id=ingredient_id, max_scan=max_scan)

    def find_tool_references(self, tool_id: int, max_scan: int = 2000) -> dict[str, Any]:
        return self._find_recipe_references(entity_key="tool_id", entity_id=tool_id, max_scan=max_scan)

    def _find_recipe_references(self, entity_key: str, entity_id: int, max_scan: int = 2000) -> dict[str, Any]:
        matched: list[dict[str, Any]] = []
        scanned = 0
        offset = 0
        page_size = min(250, max_scan)

        while scanned < max_scan:
            payload = self.list_recipes(limit=page_size, offset=offset)
            recipes = _extract_recipes(payload)
            if not recipes:
                break

            for recipe in recipes:
                scanned += 1
                if scanned > max_scan:
                    break
                if _recipe_contains_reference(recipe, entity_key=entity_key, entity_id=entity_id):
                    matched.append(
                        {
                            "id": recipe.get("id"),
                            "name": recipe.get("name"),
                        }
                    )

            if len(recipes) < page_size:
                break
            offset += page_size

        return {
            "reference_count": len(matched),
            "sample_recipes": matched[:25],
            "scanned_recipes": scanned,
            "scan_limited": scanned >= max_scan,
        }


def _extract_recipes(payload: dict[str, Any] | list[Any] | None) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("recipes", "items", "data", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _recipe_contains_reference(recipe: dict[str, Any], *, entity_key: str, entity_id: int) -> bool:
    fields = recipe.get("ingredients") if entity_key == "ingredient_id" else recipe.get("tools")
    if not isinstance(fields, list):
        return False

    for item in fields:
        if not isinstance(item, dict):
            continue
        if item.get(entity_key) == entity_id:
            return True
    return False



def _extract_recipe(payload: dict[str, Any] | list[Any] | None) -> dict[str, Any]:
    if isinstance(payload, dict):
        for key in ("recipe", "data", "item"):
            value = payload.get(key)
            if isinstance(value, dict):
                return value
        return payload
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                return item
    raise ApiError(code="invalid_recipe_payload", message="Expected recipe object from GET /api/recipes/{id}")


def _merge_recipe_update_payload(current_recipe: dict[str, Any] | list[Any] | None, incoming: dict[str, Any]) -> dict[str, Any]:
    current = _normalize_recipe_for_update(_extract_recipe(current_recipe))
    merged = dict(current)
    merged.update(incoming)
    return merged


def _normalize_recipe_for_update(recipe: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in (
        "name",
        "category",
        "subtype",
        "score",
        "tags",
        "procedure",
        "notes",
        "image_filename",
        "custom_fields",
    ):
        if key in recipe:
            out[key] = recipe.get(key)

    if "ingredients" in recipe:
        out["ingredients"] = _normalize_recipe_ingredients(recipe.get("ingredients"))
    if "tools" in recipe:
        out["tools"] = _normalize_recipe_tools(recipe.get("tools"))
    if "garnishes" in recipe:
        out["garnishes"] = _normalize_recipe_garnishes(recipe.get("garnishes"))
    return out


def _normalize_recipe_ingredients(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "ingredient_id": item.get("ingredient_id"),
                "subrecipe_id": item.get("subrecipe_id"),
                "ingredient_name": item.get("ingredient_name") or "",
                "amount": item.get("amount"),
                "unit": item.get("unit") or "",
            }
        )
    return out


def _normalize_recipe_tools(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "tool_id": item.get("tool_id"),
                "tool_name": item.get("tool_name") or "",
            }
        )
    return out


def _normalize_recipe_garnishes(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "ingredient_id": item.get("ingredient_id"),
                "garnish_text": item.get("garnish_text") or "",
            }
        )
    return out


def _assert_apply_executed(operation: str, dry_run: bool, result: dict[str, Any] | list[Any] | None) -> None:
    if dry_run or not isinstance(result, dict):
        return

    if result.get("dry_run") is True:
        raise ApiError(
            code="apply_not_executed",
            message=f"Backend reported dry_run=true for apply request in {operation}",
            details={"operation": operation, "response": result},
        )

    for bool_flag in ("apply_executed", "applied", "committed"):
        if bool_flag in result and result.get(bool_flag) is False:
            raise ApiError(
                code="apply_not_executed",
                message=f"Backend did not apply requested mutation in {operation}",
                details={"operation": operation, "response": result},
            )

    count_values: list[int] = []
    count_keys = (
        "updated",
        "updated_count",
        "updated_rows",
        "updated_recipe_count",
        "created",
        "created_count",
        "created_rows",
        "deleted",
        "deleted_count",
        "deleted_rows",
        "removed_count",
        "removed_recipe_count",
        "removed_ingredient_count",
        "removed_tool_count",
        "merged_count",
        "affected_count",
        "changed_count",
        "modified_count",
        "applied_count",
        "row_count",
        "rows_affected",
    )
    for key in count_keys:
        value = result.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            count_values.append(value)

    list_lengths: list[int] = []
    list_keys = (
        "updated_recipe_ids",
        "created_ids",
        "deleted_ids",
        "removed_ingredient_ids",
        "removed_tool_ids",
        "affected_ids",
        "changed_ids",
    )
    for key in list_keys:
        value = result.get(key)
        if isinstance(value, list):
            list_lengths.append(len(value))

    if (count_values and max(count_values) == 0) or (list_lengths and max(list_lengths) == 0):
        raise ApiError(
            code="apply_not_executed",
            message=f"Backend reported no changed rows for apply request in {operation}",
            details={"operation": operation, "response": result},
        )
