import base64

from cocktail_recipes_mcp.security import is_authorized_header


def _basic_header(username: str, password: str) -> str:
    raw = f"{username}:{password}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def test_bearer_auth_accepts_valid_token() -> None:
    assert is_authorized_header("Bearer topsecret", bearer_token="topsecret") is True
    assert is_authorized_header("Bearer wrong", bearer_token="topsecret") is False


def test_basic_auth_accepts_valid_credentials() -> None:
    assert is_authorized_header(
        _basic_header("mcpuser", "mcppass"), basic_username="mcpuser", basic_password="mcppass"
    ) is True
    assert is_authorized_header(
        _basic_header("mcpuser", "wrong"), basic_username="mcpuser", basic_password="mcppass"
    ) is False


def test_no_auth_config_means_open() -> None:
    assert is_authorized_header(None) is True
    assert is_authorized_header("anything") is True
