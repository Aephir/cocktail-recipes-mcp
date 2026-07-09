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
