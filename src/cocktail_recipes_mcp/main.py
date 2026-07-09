import uvicorn

from .config import get_settings
from .security import MCPHTTPAuthMiddleware
from .server import build_server


def main() -> None:
    settings = get_settings()
    server = build_server()

    if settings.mcp_transport == "stdio":
        server.run(transport="stdio")
        return

    app = server.streamable_http_app()
    app = MCPHTTPAuthMiddleware(
        app,
        path_prefix=settings.mcp_http_path,
        bearer_token=settings.mcp_http_bearer_token,
        basic_username=settings.mcp_http_basic_username,
        basic_password=settings.mcp_http_basic_password,
    )
    uvicorn.run(app, host=settings.mcp_http_host, port=settings.mcp_http_port)


if __name__ == "__main__":
    main()
