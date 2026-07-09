from .config import get_settings
from .server import build_server


def main() -> None:
    settings = get_settings()
    server = build_server()
    server.run(transport=settings.mcp_transport)


if __name__ == "__main__":
    main()
