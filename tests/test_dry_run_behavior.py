from typing import Any

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
    assert any(call["method"] == "DELETE" and call["path"] == "/api/admin/tools/3" for call in fake.calls)
