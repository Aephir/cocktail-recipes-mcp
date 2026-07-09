from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .client import CocktailApiClient
from .config import get_settings
from .operation_log import OperationLog
from .service import CocktailService
from .tool_registry import register_tools


def build_server() -> FastMCP:
    settings = get_settings()
    client = CocktailApiClient(settings)
    service = CocktailService(client)
    op_log = OperationLog(max_size=settings.mcp_operation_log_size)

    mcp = FastMCP(
        name=settings.mcp_server_name,
        host=settings.mcp_http_host,
        port=settings.mcp_http_port,
        streamable_http_path=settings.mcp_http_path,
    )
    register_tools(mcp, service, op_log)
    return mcp
