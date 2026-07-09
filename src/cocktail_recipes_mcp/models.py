from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorDetails(BaseModel):
    code: str
    message: str
    status_code: int | None = None
    endpoint: str | None = None
    details: dict[str, Any] | None = None


class ToolResult(BaseModel):
    ok: bool
    data: dict[str, Any] | list[Any] | None = None
    error: ErrorDetails | None = None


class CapabilityItem(BaseModel):
    action: str
    method: str
    path: str
    supported: bool
    note: str | None = None


class OperationLogItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    timestamp: datetime
    tool: str
    dry_run: bool | None = None
    status: str
    summary: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class MergeRequest(BaseModel):
    source_ids: list[int] = Field(min_length=1)
    target_id: int
    dry_run: bool = True


class RecategorizeRequest(BaseModel):
    recipe_ids: list[int] = Field(min_length=1)
    category_id: int
    dry_run: bool = True


class BulkTagsRequest(BaseModel):
    recipe_ids: list[int] = Field(min_length=1)
    add_tags: list[str] = Field(default_factory=list)
    remove_tags: list[str] = Field(default_factory=list)
    dry_run: bool = True
