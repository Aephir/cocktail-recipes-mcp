import uvicorn

from .config import get_settings
from .oauth_app import build_oauth_http_app
from .server import build_server


def main() -> None:
    settings = get_settings()
    server = build_server()

    if settings.mcp_transport == "stdio":
        server.run(transport="stdio")
        return

    app = build_oauth_http_app(server, settings)
    uvicorn.run(app, host=settings.mcp_http_host, port=settings.mcp_http_port)


if __name__ == "__main__":
    main()
