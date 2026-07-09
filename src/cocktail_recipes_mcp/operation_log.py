from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Any

from .models import OperationLogItem


class OperationLog:
    def __init__(self, max_size: int = 200) -> None:
        self._entries: deque[OperationLogItem] = deque(maxlen=max_size)

    def add(
        self,
        *,
        tool: str,
        status: str,
        summary: str,
        dry_run: bool | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._entries.appendleft(
            OperationLogItem(
                timestamp=datetime.now(timezone.utc),
                tool=tool,
                dry_run=dry_run,
                status=status,
                summary=summary,
                metadata=metadata or {},
            )
        )

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in list(self._entries)[: max(1, limit)]]
