from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
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
    public_base_url: str | None = Field(None, alias="PUBLIC_BASE_URL")
    auth_username: str | None = Field(None, alias="AUTH_USERNAME")
    auth_password: str | None = Field(None, alias="AUTH_PASSWORD")
    oauth_access_token_ttl_seconds: int = Field(3600, alias="OAUTH_ACCESS_TOKEN_TTL_SECONDS")
    oauth_refresh_token_ttl_seconds: int = Field(2592000, alias="OAUTH_REFRESH_TOKEN_TTL_SECONDS")
    oauth_authorization_code_ttl_seconds: int = Field(600, alias="OAUTH_AUTHORIZATION_CODE_TTL_SECONDS")
    oauth_storage_dir: str = Field("/data/oauth", alias="OAUTH_STORAGE_DIR")
    oauth_jwt_key_path: str = Field("/data/oauth/jwt_signing_key.pem", alias="OAUTH_JWT_KEY_PATH")
    oauth_client_redirect_allowlist: str | None = Field(None, alias="OAUTH_CLIENT_REDIRECT_ALLOWLIST")

    @model_validator(mode="after")
    def validate_oauth_settings(self) -> "Settings":
        oauth_user_set = bool(self.auth_username)
        oauth_pass_set = bool(self.auth_password)
        if oauth_user_set != oauth_pass_set:
            raise ValueError("AUTH_USERNAME and AUTH_PASSWORD must both be set or both be unset")

        if self.mcp_transport == "streamable-http":
            if not self.public_base_url:
                raise ValueError("PUBLIC_BASE_URL must be set when MCP_TRANSPORT=streamable-http")
            if not oauth_user_set:
                raise ValueError("AUTH_USERNAME and AUTH_PASSWORD must be set when MCP_TRANSPORT=streamable-http")

        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
