from enum import StrEnum

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SecondKeyMode(StrEnum):
    """How the second device key is issued."""

    manual_approval = "manual_approval"
    auto = "auto"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    telegram_bot_token: str = Field(..., alias="TELEGRAM_BOT_TOKEN")
    admin_telegram_id: int = Field(..., alias="ADMIN_TELEGRAM_ID")
    support_telegram_username: str = Field(
        "voronin_36",
        alias="SUPPORT_TELEGRAM_USERNAME",
        description="Username поддержки без @ — для текстов пользователю",
    )

    # Database
    database_url: str = Field(
        ...,
        alias="DATABASE_URL",
        description="asyncpg URL, e.g. postgresql+asyncpg://user:pass@host:5432/dbname",
    )

    # 3x-ui panel
    panel_base_url: str = Field(
        ...,
        alias="PANEL_BASE_URL",
        description="Root URL of panel, e.g. https://127.0.0.1:2053 (no trailing path)",
    )
    panel_username: str = Field(..., alias="PANEL_USERNAME")
    panel_password: str = Field(..., alias="PANEL_PASSWORD")
    panel_verify_tls: bool = Field(True, alias="PANEL_VERIFY_TLS")
    panel_request_timeout_sec: float = Field(30.0, alias="PANEL_REQUEST_TIMEOUT_SEC")
    panel_max_retries: int = Field(3, alias="PANEL_MAX_RETRIES", ge=1, le=10)

    default_inbound_id: int = Field(..., alias="DEFAULT_INBOUND_ID")
    second_device_inbound_id: int | None = Field(
        None,
        alias="SECOND_DEVICE_INBOUND_ID",
        description="If unset, second key uses DEFAULT_INBOUND_ID",
    )

    panel_update_remark_on_bind: bool = Field(
        False,
        alias="PANEL_UPDATE_REMARK_ON_BIND",
        description="If true, optional panel call on bind (default off per spec)",
    )

    panel_client_flow: str = Field(
        "xtls-rprx-vision",
        alias="PANEL_CLIENT_FLOW",
        description="VLESS flow в addClient (3x-ui), напр. xtls-rprx-vision. Пустое значение в env — не слать flow "
        "(например, только VMess).",
    )

    panel_client_link_host: str | None = Field(
        None,
        alias="PANEL_CLIENT_LINK_HOST",
        description="Публичный адрес (домен/IP) в vless://@host:port, если inbound listen=0.0.0.0. "
        "Иначе берётся listen, иначе hostname из PANEL_BASE_URL.",
    )

    subscription_public_base_url: str | None = Field(
        None,
        alias="SUBSCRIPTION_PUBLIC_BASE_URL",
        description="База для /sub/… (опционально); не используется в основной выдаче ключа пользователю.",
    )

    # API path overrides (adapter assumptions)
    panel_login_path: str = Field("/login", alias="PANEL_LOGIN_PATH")
    panel_api_list_inbounds: str = Field(
        "/panel/api/inbounds/list", alias="PANEL_API_LIST_INBOUNDS"
    )
    panel_api_add_client: str = Field("/panel/api/inbounds/addClient", alias="PANEL_API_ADD_CLIENT")
    panel_api_update_client: str = Field(
        "/panel/api/inbounds/updateClient", alias="PANEL_API_UPDATE_CLIENT"
    )
    panel_api_del_client: str = Field(
        "/panel/api/inbounds/delClientByEmail", alias="PANEL_API_DEL_CLIENT"
    )
    panel_api_client_traffic: str = Field(
        "/panel/api/inbounds/getClientTraffics/{email}",
        validation_alias=AliasChoices("PANEL_API_CLIENT_TRAFFIC", "PANEL_API_INBOUND_CLIENT_TRAFFIC"),
        description="GET getClientTraffics/:email — параметр это **email клиента** в панели (3x-ui), не inbound id.",
    )


    second_key_mode: SecondKeyMode = Field(
        SecondKeyMode.manual_approval, alias="SECOND_KEY_MODE"
    )

    regenerate_cooldown_sec: int = Field(300, alias="REGENERATE_COOLDOWN_SEC", ge=60)
    regenerate_max_per_day: int = Field(5, alias="REGENERATE_MAX_PER_DAY", ge=1)

    log_level: str = Field("INFO", alias="LOG_LEVEL")

    @field_validator("database_url")
    @classmethod
    def database_url_asyncpg(cls, v: str) -> str:
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use postgresql+asyncpg:// scheme")
        return v


def get_settings() -> Settings:
    return Settings()
