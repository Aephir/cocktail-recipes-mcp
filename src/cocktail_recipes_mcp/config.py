from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    cocktail_api_base_url: str = Field(..., alias="COCKTAIL_API_BASE_URL")
    cocktail_api_username: str = Field(..., alias="COCKTAIL_API_USERNAME")
    cocktail_api_password: str = Field(..., alias="COCKTAIL_API_PASSWORD")
    cocktail_api_login_path: str = Field("/api/auth/login", alias="COCKTAIL_API_LOGIN_PATH")
    cocktail_api_timeout_seconds: float = Field(15.0, alias="COCKTAIL_API_TIMEOUT_SECONDS")
    cocktail_api_max_retries: int = Field(3, alias="COCKTAIL_API_MAX_RETRIES")
    cocktail_api_retry_backoff_seconds: float = Field(0.5, alias="COCKTAIL_API_RETRY_BACKOFF_SECONDS")

    mcp_operation_log_size: int = Field(200, alias="MCP_OPERATION_LOG_SIZE")
    mcp_server_name: str = Field("cocktail-recipes-mcp", alias="MCP_SERVER_NAME")
    mcp_server_version: str = Field("0.1.0", alias="MCP_SERVER_VERSION")
    mcp_transport: Literal["stdio", "streamable-http"] = Field("stdio", alias="MCP_TRANSPORT")
    mcp_http_host: str = Field("0.0.0.0", alias="MCP_HTTP_HOST")
    mcp_http_port: int = Field(8000, alias="MCP_HTTP_PORT")
    mcp_http_path: str = Field("/mcp", alias="MCP_HTTP_PATH")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
