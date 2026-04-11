from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class InboundSummary(BaseModel):
    id: int
    remark: str | None = None
    protocol: str | None = None
    port: int | None = None


class PanelClientRow(BaseModel):
    """One client row as seen on panel (for import)."""

    inbound_id: int
    email: str = Field(..., description="Panel 'email' field (client id label)")
    uuid: str | None = None
    remark: str | None = None
    sub_id: str | None = None
    enable: bool = True
    #: ASSUMPTION: x-ui/3x-ui часто кладёт ``lastOnline`` в мс (0 = «ещё не было»)
    last_seen_utc: datetime | None = None


class CreatedClient(BaseModel):
    inbound_id: int
    email: str
    uuid: str | None = None
    sub_id: str | None = None


class ClientTrafficRow(BaseModel):
    """Per-client traffic as returned by panel (3x-ui / x-ui family).

    Values are treated as **bytes** for up/down when they look like byte counters.
    If the panel uses other units, override parsing in the adapter.
    """

    client_email: str
    upload_bytes: int = 0
    download_bytes: int = 0
    #: поле ``allTime`` в JSON 3x-ui (накопительно), если есть
    all_time_bytes: int = 0
    #: Extension: некоторые сборки добавляют lastOnline / online в ответ трафика
    last_seen_utc: datetime | None = None
    online: bool | None = None

    def total_use_bytes(self) -> int:
        """Для отображения: предпочитаем allTime, иначе up+down."""
        if self.all_time_bytes > 0:
            return self.all_time_bytes
        return self.upload_bytes + self.download_bytes


@runtime_checkable
class VpnPanelClient(Protocol):
    """Integration boundary for VPN panel (3x-ui adapter).

    All HTTP/path assumptions live in the implementation, not in handlers.
    """

    async def healthcheck(self) -> list[InboundSummary]:
        """Login (if needed) and return inbound list — for /admin_panel_check."""

    async def list_inbounds(self) -> list[InboundSummary]:
        ...

    async def list_clients_in_inbound(self, inbound_id: int) -> list[PanelClientRow]:
        ...

    async def fetch_inbound_raw(self, inbound_id: int) -> dict[str, Any]:
        """Полная строка inbound из API list (для сборки vless://)."""

    async def verify_client_created(
        self, inbound_id: int, email: str, client_uuid: str
    ) -> PanelClientRow:
        """Убедиться, что клиент виден в inbound после addClient."""

    def build_vless_share_link(
        self,
        inbound_row: dict[str, Any],
        *,
        client_uuid: str,
        client_flow: str | None,
        remark: str,
    ) -> str:
        """Прямой vless:// для клиента; только inbound с protocol=vless."""

    async def create_client(
        self,
        inbound_id: int,
        email: str,
        remark: str | None = None,
        telegram_user_id: int | None = None,
    ) -> CreatedClient:
        ...

    async def delete_client_by_email(self, inbound_id: int, email: str) -> None:
        """Remove or disable client — ASSUMPTION: delClientByEmail style API."""

    async def update_client_remark(
        self,
        inbound_id: int,
        email: str,
        new_remark: str,
    ) -> None:
        """Only used when config enables remark sync; default implementation may no-op."""

    def build_subscription_link(self, sub_id: str | None, email: str, inbound_id: int) -> str:
        """Return a share/subscription URL for user (no secrets in DB; may be built from subId)."""

    async def fetch_client_traffics_by_emails(
        self, emails: list[str]
    ) -> dict[str, ClientTrafficRow] | None:
        """Трафик по списку panel client email (3x-ui: GET getClientTraffics/:email).

        - ``None`` — критический сбой (ни один запрос не удался при необходимости).
        - ``{}`` — пустой вход или все запросы без данных.
        Ключ — ``email`` клиента в панели.
        """
