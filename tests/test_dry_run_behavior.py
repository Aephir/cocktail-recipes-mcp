from typing import Any

import pytest

from cocktail_recipes_mcp.errors import ApiError
from cocktail_recipes_mcp.models import MergeRequest
from cocktail_recipes_mcp.service import CocktailService


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"method": method, "path": path, **kwargs})
        return {"ok": True, "echo": kwargs}


def test_delete_recipe_defaults_to_dry_run() -> None:
    service = CocktailService(client=FakeClient())
    result = service.delete_recipe(recipe_id=7)

    assert result["apply_executed"] is False
    assert result["preview"]["dry_run"] is True


def test_create_recipe_defaults_to_dry_run_and_applies_explicitly() -> None:
    fake = FakeClient()
    service = CocktailService(client=fake)

    preview = service.create_recipe(payload={"name": "Martini"})
    applied = service.create_recipe(payload={"name": "Martini"}, dry_run=False)

    assert preview["apply_executed"] is False
    assert preview["preview"]["dry_run"] is True
    assert applied["apply_executed"] is True
    assert fake.calls[0]["method"] == "POST"


def test_merge_ingredients_dry_run_and_apply_flags() -> None:
    fake = FakeClient()
    service = CocktailService(client=fake)

    service.merge_ingredients(MergeRequest(source_ids=[10], target_id=11, dry_run=True))
    service.merge_ingredients(MergeRequest(source_ids=[10], target_id=11, dry_run=False))

    assert fake.calls[0]["idempotent"] is True
    assert fake.calls[0]["json"]["dry_run"] is True

    assert fake.calls[1]["idempotent"] is False
    assert fake.calls[1]["json"]["dry_run"] is False

def test_merge_ingredients_contract_sends_source_ids_list() -> None:
    fake = FakeClient()
    service = CocktailService(client=fake)

    service.merge_ingredients(MergeRequest(source_ids=[10, 12], target_id=11, dry_run=False))

    payload = fake.calls[0]["json"]
    assert payload["source_ids"] == [10, 12]
    assert "source_id" not in payload


def test_merge_tools_contract_sends_source_ids_list() -> None:
    fake = FakeClient()
    service = CocktailService(client=fake)

    service.merge_tools(MergeRequest(source_ids=[20, 21], target_id=22, dry_run=False))

    payload = fake.calls[0]["json"]
    assert payload["source_ids"] == [20, 21]
    assert "source_id" not in payload


def test_create_ingredient_dry_run_and_apply_flags() -> None:
    fake = FakeClient()
    service = CocktailService(client=fake)

    preview = service.create_ingredient(name="Lime")
    applied = service.create_ingredient(name="Lime", dry_run=False)

    assert preview["apply_executed"] is False
    assert preview["preview"]["dry_run"] is True
    assert applied["apply_executed"] is True
    assert fake.calls[-1]["path"] == "/api/admin/ingredients"


def test_delete_ingredient_blocks_apply_when_referenced_and_not_forced() -> None:
    class RefClient(FakeClient):
        def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any] | list[dict[str, Any]]:
            if method == "GET" and path == "/api/recipes":
                return [
                    {
                        "id": 1,
                        "name": "Daiquiri",
                        "ingredients": [{"ingredient_id": 7, "ingredient_name": "Lime"}],
                    }
                ]
            return super().request(method, path, **kwargs)

    fake = RefClient()
    service = CocktailService(client=fake)

    result = service.delete_ingredient(ingredient_id=7, dry_run=False, force=False)

    assert result["apply_executed"] is False
    assert result["blocked"] is True
    assert result["preview"]["warning"]["details"]["reference_count"] == 1
    assert all(call["method"] != "DELETE" for call in fake.calls)


def test_delete_tool_force_applies_even_when_referenced() -> None:
    class RefClient(FakeClient):
        def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any] | list[dict[str, Any]]:
            if method == "GET" and path == "/api/recipes":
                return [
                    {
                        "id": 2,
                        "name": "Old Fashioned",
                        "tools": [{"tool_id": 3, "tool_name": "Mixing Glass"}],
                    }
                ]
            return super().request(method, path, **kwargs)

    fake = RefClient()
    service = CocktailService(client=fake)

    result = service.delete_tool(tool_id=3, dry_run=False, force=True)

    assert result["apply_executed"] is True
    delete_call = next(call for call in fake.calls if call["method"] == "DELETE")
    assert delete_call["path"] == "/api/admin/tools/3"
    assert delete_call["params"] == {"dry_run": False, "force": True}
    assert delete_call["json"] == {"dry_run": False, "force": True}


def test_delete_ingredient_apply_sends_dry_run_false_and_force() -> None:
    fake = FakeClient()
    service = CocktailService(client=fake)

    result = service.delete_ingredient(ingredient_id=7, dry_run=False, force=False)

    assert result["apply_executed"] is True
    delete_call = next(call for call in fake.calls if call["method"] == "DELETE")
    assert delete_call["path"] == "/api/admin/ingredients/7"
    assert delete_call["params"] == {"dry_run": False, "force": False}
    assert delete_call["json"] == {"dry_run": False, "force": False}


def test_bulk_update_recipes_dry_run_and_apply_flags() -> None:
    fake = FakeClient()
    service = CocktailService(client=fake)

    filters = {"apply_all": False, "recipe_ids": [1, 2]}
    updates = {"tags_add": ["citrus"]}

    preview = service.bulk_update_recipes(filters=filters, updates=updates, dry_run=True)
    applied = service.bulk_update_recipes(filters=filters, updates=updates, dry_run=False)

    assert preview["apply_executed"] is False
    assert preview["preview"]["operation"] == "bulk_update_recipes"
    assert fake.calls[0]["idempotent"] is True
    assert fake.calls[0]["path"] == "/api/admin/recipes/bulk-update"

    assert applied["apply_executed"] is True
    assert fake.calls[1]["idempotent"] is False
    assert fake.calls[1]["path"] == "/api/admin/recipes/bulk-update"


def test_apply_errors_when_backend_reports_dry_run_true() -> None:
    class DryRunApplyClient(FakeClient):
        def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
            self.calls.append({"method": method, "path": path, **kwargs})
            if method == "POST" and path == "/api/admin/ingredients":
                return {"dry_run": True, "apply_executed": True}
            return {"ok": True}

    service = CocktailService(client=DryRunApplyClient())

    with pytest.raises(ApiError, match="dry_run=true"):
        service.create_ingredient(name="Lime", dry_run=False)


def test_apply_errors_when_backend_reports_no_changes() -> None:
    class NoChangeApplyClient(FakeClient):
        def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
            self.calls.append({"method": method, "path": path, **kwargs})
            if method == "POST" and path == "/api/admin/tools/merge":
                return {"updated_recipe_count": 0, "removed_tool_ids": []}
            return {"ok": True}

    service = CocktailService(client=NoChangeApplyClient())

    with pytest.raises(ApiError, match="no changed rows"):
        service.merge_tools(MergeRequest(source_ids=[1], target_id=2, dry_run=False))


def test_delete_apply_errors_when_backend_reports_dry_run_true() -> None:
    class DryRunDeleteClient(FakeClient):
        def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any] | list[Any]:
            self.calls.append({"method": method, "path": path, **kwargs})
            if method == "GET" and path == "/api/recipes":
                return []
            if method == "DELETE" and path == "/api/admin/tools/3":
                return {"dry_run": True, "apply_executed": True}
            return {"ok": True}

    service = CocktailService(client=DryRunDeleteClient())

    with pytest.raises(ApiError, match="dry_run=true"):
        service.delete_tool(tool_id=3, dry_run=False, force=False)


def test_update_recipe_apply_fetches_and_preserves_omitted_lists() -> None:
    class RecipeClient(FakeClient):
        def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
            self.calls.append({"method": method, "path": path, **kwargs})
            if method == "GET" and path == "/api/recipes/7":
                return {
                    "id": 7,
                    "name": "Old Name",
                    "category": "Cocktail",
                    "subtype": "Sour",
                    "score": 8,
                    "tags": ["classic"],
                    "procedure": "Shake",
                    "notes": "",
                    "image_filename": None,
                    "ingredients": [
                        {
                            "ingredient_id": 1,
                            "ingredient_name": "Gin",
                            "amount": 2,
                            "unit": "oz",
                            "order": 1,
                            "subrecipe_id": None,
                            "subrecipe_name": None,
                        }
                    ],
                    "tools": [{"tool_id": 5, "tool_name": "Shaker"}],
                    "garnishes": [
                        {
                            "ingredient_id": 9,
                            "ingredient_name": "Lemon Twist",
                            "garnish_text": "Lemon twist",
                            "order": 1,
                        }
                    ],
                    "custom_fields": {},
                }
            if method == "PUT" and path == "/api/recipes/7":
                return {"updated": 1}
            return {"ok": True}

    fake = RecipeClient()
    service = CocktailService(client=fake)

    result = service.update_recipe(recipe_id=7, payload={"name": "New Name"}, dry_run=False)

    assert result["apply_executed"] is True
    put_call = next(call for call in fake.calls if call["method"] == "PUT")
    payload = put_call["json"]
    assert payload["name"] == "New Name"
    assert payload["tools"] == [{"tool_id": 5, "tool_name": "Shaker"}]
    assert payload["garnishes"] == [{"ingredient_id": 9, "garnish_text": "Lemon twist"}]
