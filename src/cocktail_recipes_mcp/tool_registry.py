from __future__ import annotations

from typing import Any

from pydantic import ValidationError
from mcp.types import ToolAnnotations

from .errors import ApiError, error_result, not_implemented_result, ok_result
from .models import BulkTagsRequest, MergeRequest, RecategorizeRequest
from .operation_log import OperationLog
from .service import CocktailService


def register_tools(mcp: Any, service: CocktailService, op_log: OperationLog) -> None:
    read_only_annotations = ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
    additive_write_annotations = ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    )
    mutating_write_annotations = ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    )

    def _run(tool_name: str, dry_run: bool | None, fn: Any) -> dict[str, Any]:
        try:
            data = fn()
            op_log.add(
                tool=tool_name,
                dry_run=dry_run,
                status="ok",
                summary=f"{tool_name} completed",
                metadata={"has_data": data is not None},
            )
            return ok_result(data if data is not None else {"message": "ok"})
        except ValidationError as exc:
            error = ApiError(code="validation_error", message="Invalid tool arguments", details={"errors": exc.errors()})
            op_log.add(tool=tool_name, dry_run=dry_run, status="error", summary=error.message)
            return error_result(error)
        except ApiError as exc:
            op_log.add(tool=tool_name, dry_run=dry_run, status="error", summary=exc.message)
            if exc.code == "not_implemented":
                return not_implemented_result(tool_name, exc.endpoint or "unknown")
            return error_result(exc)
        except Exception as exc:  # pragma: no cover
            error = ApiError(code="internal_error", message="Unexpected MCP tool failure", details={"error": str(exc)})
            op_log.add(tool=tool_name, dry_run=dry_run, status="error", summary=error.message)
            return error_result(error)

    @mcp.tool(annotations=read_only_annotations)
    def list_recipes(limit: int = 100, offset: int = 0) -> dict[str, Any]:
        return _run("list_recipes", None, lambda: service.list_recipes(limit=limit, offset=offset))

    @mcp.tool(annotations=read_only_annotations)
    def get_recipe(recipe_id: int) -> dict[str, Any]:
        return _run("get_recipe", None, lambda: service.get_recipe(recipe_id=recipe_id))

    @mcp.tool(annotations=additive_write_annotations)
    def create_recipe(payload: dict[str, Any], dry_run: bool = True) -> dict[str, Any]:
        return _run("create_recipe", dry_run, lambda: service.create_recipe(payload=payload, dry_run=dry_run))

    @mcp.tool(annotations=mutating_write_annotations)
    def update_recipe(recipe_id: int, payload: dict[str, Any], dry_run: bool = True) -> dict[str, Any]:
        return _run(
            "update_recipe",
            dry_run,
            lambda: service.update_recipe(recipe_id=recipe_id, payload=payload, dry_run=dry_run),
        )

    @mcp.tool(annotations=mutating_write_annotations)
    def delete_recipe(recipe_id: int, dry_run: bool = True) -> dict[str, Any]:
        return _run("delete_recipe", dry_run, lambda: service.delete_recipe(recipe_id=recipe_id, dry_run=dry_run))

    @mcp.tool(annotations=read_only_annotations)
    def list_ingredients(limit: int = 250, offset: int = 0) -> dict[str, Any]:
        return _run("list_ingredients", None, lambda: service.list_ingredients(limit=limit, offset=offset))

    @mcp.tool(annotations=read_only_annotations)
    def list_tools(limit: int = 250, offset: int = 0) -> dict[str, Any]:
        return _run("list_tools", None, lambda: service.list_tools(limit=limit, offset=offset))

    @mcp.tool(annotations=mutating_write_annotations)
    def merge_ingredients(source_ids: list[int], target_id: int, dry_run: bool = True) -> dict[str, Any]:
        def _fn() -> dict[str, Any]:
            req = MergeRequest(source_ids=source_ids, target_id=target_id, dry_run=dry_run)
            preview = {
                "operation": "merge_ingredients",
                "dry_run": dry_run,
                "affected": {
                    "source_ids": req.source_ids,
                    "target_id": req.target_id,
                    "count": len(req.source_ids),
                },
            }
            result = service.merge_ingredients(req)
            return {"preview": preview, "apply_executed": not dry_run, "result": result}

        return _run("merge_ingredients", dry_run, _fn)

    @mcp.tool(annotations=mutating_write_annotations)
    def merge_tools(source_ids: list[int], target_id: int, dry_run: bool = True) -> dict[str, Any]:
        def _fn() -> dict[str, Any]:
            req = MergeRequest(source_ids=source_ids, target_id=target_id, dry_run=dry_run)
            preview = {
                "operation": "merge_tools",
                "dry_run": dry_run,
                "affected": {
                    "source_ids": req.source_ids,
                    "target_id": req.target_id,
                    "count": len(req.source_ids),
                },
            }
            result = service.merge_tools(req)
            return {"preview": preview, "apply_executed": not dry_run, "result": result}

        return _run("merge_tools", dry_run, _fn)

    @mcp.tool(annotations=mutating_write_annotations)
    def recategorize_recipes(recipe_ids: list[int], category_id: int, dry_run: bool = True) -> dict[str, Any]:
        def _fn() -> dict[str, Any]:
            req = RecategorizeRequest(recipe_ids=recipe_ids, category_id=category_id, dry_run=dry_run)
            preview = {
                "operation": "recategorize_recipes",
                "dry_run": dry_run,
                "affected": {
                    "recipe_ids": req.recipe_ids,
                    "category_id": req.category_id,
                    "count": len(req.recipe_ids),
                },
            }
            result = service.recategorize_recipes(req)
            return {"preview": preview, "apply_executed": not dry_run, "result": result}

        return _run("recategorize_recipes", dry_run, _fn)

    @mcp.tool(annotations=mutating_write_annotations)
    def update_tags_bulk(
        recipe_ids: list[int],
        add_tags: list[str] | None = None,
        remove_tags: list[str] | None = None,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        def _fn() -> dict[str, Any]:
            req = BulkTagsRequest(
                recipe_ids=recipe_ids,
                add_tags=add_tags or [],
                remove_tags=remove_tags or [],
                dry_run=dry_run,
            )
            preview = {
                "operation": "update_tags_bulk",
                "dry_run": dry_run,
                "affected": {
                    "recipe_ids": req.recipe_ids,
                    "count": len(req.recipe_ids),
                    "add_tags": req.add_tags,
                    "remove_tags": req.remove_tags,
                },
            }
            result = service.update_tags_bulk(req)
            return {"preview": preview, "apply_executed": not dry_run, "result": result}

        return _run("update_tags_bulk", dry_run, _fn)

    @mcp.tool(annotations=read_only_annotations)
    def operation_log_recent(limit: int = 20) -> dict[str, Any]:
        return _run("operation_log_recent", None, lambda: {"entries": op_log.recent(limit=limit)})

    @mcp.tool(annotations=read_only_annotations)
    def api_capabilities() -> dict[str, Any]:
        return _run("api_capabilities", None, lambda: {"capabilities": service.api_capabilities()})
