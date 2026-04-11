"""3x-ui HTTP adapter.

ASSUMPTIONS (adjust paths via env if your panel version differs):
- Session auth: POST ``PANEL_LOGIN_PATH`` with form fields ``username``, ``password`` sets cookies.
- ``GET PANEL_API_LIST_INBOUNDS`` returns JSON ``{ "success": true, "obj": [ inbound, ... ] }``.
- Each inbound may expose ``settings`` as a JSON **string** containing ``clients`` array (x-ui family).
- ``POST PANEL_API_ADD_CLIENT`` accepts ``{ "id": inboundId, "settings": "<json string>" }``
  where settings contains ``clients`` array with one new client.
- ``GET .../getClientTraffics/{email}`` — трафик **одного** клиента; в пути **email** клиента (не id inbound). См. 3x-ui ``InboundController.getClientTraffics``.
- ``POST PANEL_API_DEL_CLIENT`` accepts ``{ "id": inboundId, "email": "<client email>" }``.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
import secrets
import uuid
from typing import Any
from urllib.parse import quote
import httpx
import structlog

from app.core.config import Settings
from app.integrations.three_x_ui.errors import (
    PanelAuthError,
    PanelBadRequestError,
    PanelClientVerificationError,
    PanelNotFoundError,
    PanelShareLinkError,
    PanelTransientError,
)
from app.integrations.three_x_ui.vless_link import build_vless_share_url
from app.integrations.three_x_ui.protocol import (
    ClientTrafficRow,
    CreatedClient,
    InboundSummary,
    PanelClientRow,
)

log = structlog.get_logger(__name__)


def _parse_last_online_ms(raw: Any) -> datetime | None:
    """ASSUMPTION: ``lastOnline`` в мс с эпохи; 0 или отсутствие = нет данных."""
    if raw is None:
        return None
    try:
        ms = int(float(raw))
    except (TypeError, ValueError):
        return None
    if ms <= 0:
        return None
    return datetime.fromtimestamp(ms / 1000.0, tz=UTC)


def _parse_online_flag(raw: Any) -> bool | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    if isinstance(raw, str):
        return raw.lower() in ("true", "1", "yes")
    return None


def _traffic_to_bytes(value: Any) -> int:
    """ASSUMPTION: 3x-ui отдаёт up/down как байты (частый случай в x-ui)."""
    if value is None:
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _redact_for_log(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _redact_for_log(v) for k, v in obj.items() if k.lower() not in ("password", "obj")}
    if isinstance(obj, list):
        return [_redact_for_log(x) for x in obj[:20]]
    if isinstance(obj, str) and len(obj) > 120:
        return obj[:40] + "…"
    return obj


class ThreeXUiAdapter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: httpx.AsyncClient | None = None
        self._login_lock = asyncio.Lock()

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._settings.panel_base_url.rstrip("/") + "/",
                verify=self._settings.panel_verify_tls,
                timeout=self._settings.panel_request_timeout_sec,
                follow_redirects=True,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any | None = None,
        data: dict[str, str] | None = None,
    ) -> Any:
        client = await self._ensure_client()
        last_exc: Exception | None = None
        for attempt in range(self._settings.panel_max_retries):
            try:
                resp = await client.request(method, path.lstrip("/"), json=json_body, data=data)
                if resp.status_code in (502, 503, 504):
                    raise PanelTransientError(f"HTTP {resp.status_code}")
                if resp.status_code == 401 or resp.status_code == 403:
                    async with self._login_lock:
                        await self._login_unlocked()
                    continue
                payload = resp.json() if resp.content else {}
                return payload
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_exc = e
                await asyncio.sleep(0.3 * (attempt + 1))
        if last_exc:
            raise PanelTransientError(str(last_exc)) from last_exc
        raise PanelTransientError("exhausted retries")

    async def _login_unlocked(self) -> None:
        # ASSUMPTION: form login; some builds expect JSON — switch here if needed.
        client = await self._ensure_client()
        path = self._settings.panel_login_path.lstrip("/")
        data = {
            "username": self._settings.panel_username,
            "password": self._settings.panel_password,
        }
        resp = await client.post(path, data=data)
        if resp.status_code >= 400:
            log.warning("panel_login_failed", status=resp.status_code)
            raise PanelAuthError("login failed")
        try:
            body = resp.json()
        except Exception:
            body = {}
        if isinstance(body, dict) and body.get("success") is False:
            log.warning("panel_login_rejected", body=_redact_for_log(body))
            raise PanelAuthError("login rejected")
        log.info("panel_login_ok")

    async def login(self) -> None:
        async with self._login_lock:
            await self._login_unlocked()

    def _assert_success(self, payload: Any, context: str) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise PanelBadRequestError(f"{context}: non-dict response")
        if not payload.get("success", True):
            msg = str(payload.get("msg") or payload.get("message") or "panel error")
            log.warning("panel_call_failed", context=context, msg=msg[:200])
            raise PanelBadRequestError(msg)
        return payload

    async def healthcheck(self) -> list[InboundSummary]:
        await self.login()
        return await self.list_inbounds()

    async def list_inbounds(self) -> list[InboundSummary]:
        await self.login()
        raw = await self._request(
            "GET",
            self._settings.panel_api_list_inbounds,
        )
        data = self._assert_success(raw, "list_inbounds")
        obj = data.get("obj")
        if not isinstance(obj, list):
            return []
        out: list[InboundSummary] = []
        for row in obj:
            if not isinstance(row, dict):
                continue
            try:
                rid = int(row.get("id"))
            except (TypeError, ValueError):
                continue
            out.append(
                InboundSummary(
                    id=rid,
                    remark=row.get("remark"),
                    protocol=row.get("protocol"),
                    port=row.get("port"),
                )
            )
        return out

    def _parse_clients_from_inbound(self, inbound_id: int, inbound_row: dict[str, Any]) -> list[PanelClientRow]:
        settings_raw = inbound_row.get("settings")
        if not settings_raw or not isinstance(settings_raw, str):
            return []
        try:
            settings = json.loads(settings_raw)
        except json.JSONDecodeError:
            return []
        clients = settings.get("clients")
        if not isinstance(clients, list):
            return []
        rows: list[PanelClientRow] = []
        for c in clients:
            if not isinstance(c, dict):
                continue
            email = c.get("email")
            if not email:
                continue
            rows.append(
                PanelClientRow(
                    inbound_id=inbound_id,
                    email=str(email),
                    uuid=c.get("id"),
                    remark=c.get("remark"),
                    sub_id=c.get("subId"),
                    enable=bool(c.get("enable", True)),
                    last_seen_utc=_parse_last_online_ms(c.get("lastOnline")),
                )
            )
        return rows

    def _traffic_row_from_api_dict(self, row: dict[str, Any], request_email: str) -> ClientTrafficRow:
        em = str(row.get("email") or request_email)
        up_b = _traffic_to_bytes(row.get("up"))
        down_b = _traffic_to_bytes(row.get("down"))
        all_b = _traffic_to_bytes(row.get("allTime"))
        return ClientTrafficRow(
            client_email=em,
            upload_bytes=up_b,
            download_bytes=down_b,
            all_time_bytes=all_b,
            last_seen_utc=_parse_last_online_ms(row.get("lastOnline")),
            online=_parse_online_flag(row.get("online")),
        )

    async def _fetch_one_client_traffic(
        self, request_email: str
    ) -> tuple[str, ClientTrafficRow | None]:
        """Один GET getClientTraffics/:email; email в path — url-encoded."""
        path = self._settings.panel_api_client_traffic.format(
            email=quote(str(request_email), safe="")
        ).lstrip("/")
        try:
            raw = await self._request("GET", path)
            data = self._assert_success(raw, "get_client_traffic")
        except (PanelBadRequestError, PanelNotFoundError, PanelTransientError) as e:
            log.warning(
                "panel_traffic_email_failed",
                email=request_email[:64],
                err=str(e)[:200],
            )
            return (request_email, None)
        except Exception as e:
            log.warning("panel_traffic_email_error", email=request_email[:64], err=str(e)[:200])
            return (request_email, None)
        obj = data.get("obj")
        rows: list[dict[str, Any]] = []
        if isinstance(obj, dict):
            rows = [obj]
        elif isinstance(obj, list):
            rows = [r for r in obj if isinstance(r, dict)]
        if not rows:
            return (request_email, None)
        row = rows[0]
        ctr = self._traffic_row_from_api_dict(row, request_email)
        return (request_email, ctr)

    async def fetch_client_traffics_by_emails(
        self, emails: list[str]
    ) -> dict[str, ClientTrafficRow] | None:
        """3x-ui: ``GET .../getClientTraffics/{email}`` — по **email** клиента (не inbound id).

        Несколько ключей → несколько запросов (параллельно). ``None``, если по всем email запросы
        завершились ошибкой (нет ни одной строки трафика).
        """
        unique = sorted({e for e in emails if e})
        if not unique:
            return {}
        await self.login()
        results = await asyncio.gather(
            *[self._fetch_one_client_traffic(e) for e in unique],
            return_exceptions=True,
        )
        out: dict[str, ClientTrafficRow] = {}
        for r in results:
            if isinstance(r, BaseException):
                log.warning("panel_traffic_gather_exc", err=str(r)[:120])
                continue
            req_email, ctr = r
            if ctr is not None:
                out[req_email] = ctr

        if not out and unique:
            return None
        return out

    async def list_clients_in_inbound(self, inbound_id: int) -> list[PanelClientRow]:
        await self.login()
        raw = await self._request("GET", self._settings.panel_api_list_inbounds)
        data = self._assert_success(raw, "list_inbounds_for_clients")
        obj = data.get("obj")
        if not isinstance(obj, list):
            return []
        for row in obj:
            if isinstance(row, dict) and int(row.get("id") or -1) == inbound_id:
                return self._parse_clients_from_inbound(inbound_id, row)
        raise PanelNotFoundError(f"inbound {inbound_id} not found")

    async def fetch_inbound_raw(self, inbound_id: int) -> dict[str, Any]:
        """Полная строка inbound из list (streamSettings/settings как JSON-строки)."""
        await self.login()
        raw = await self._request("GET", self._settings.panel_api_list_inbounds)
        data = self._assert_success(raw, "fetch_inbound_raw")
        obj = data.get("obj")
        if not isinstance(obj, list):
            raise PanelNotFoundError("inbounds list empty")
        for row in obj:
            if isinstance(row, dict) and int(row.get("id") or -1) == inbound_id:
                return row
        raise PanelNotFoundError(f"inbound {inbound_id} not found")

    def _resolve_client_link_host(self, inbound_row: dict[str, Any]) -> str:
        """Адрес в URI: явный env, иначе listen, иначе hostname из PANEL_BASE_URL."""
        if (self._settings.panel_client_link_host or "").strip():
            return (self._settings.panel_client_link_host or "").strip()
        listen = str(inbound_row.get("listen") or "").strip()
        if listen and listen not in ("0.0.0.0", "::", "[::]"):
            return listen
        from urllib.parse import urlparse

        host = urlparse(self._settings.panel_base_url).hostname
        if host:
            return host
        raise PanelShareLinkError(
            "Не удалось определить адрес для ключа: задайте PANEL_CLIENT_LINK_HOST "
            "(inbound слушает 0.0.0.0 или URL панели без хоста)."
        )

    async def verify_client_created(
        self, inbound_id: int, email: str, client_uuid: str
    ) -> PanelClientRow:
        """Пост-проверка после addClient: клиент с тем же email и uuid в списке inbound."""
        want = (client_uuid or "").strip().lower()
        clients = await self.list_clients_in_inbound(inbound_id)
        for c in clients:
            if c.email != email:
                continue
            got = (c.uuid or "").strip().lower()
            if got == want:
                if not c.enable:
                    raise PanelClientVerificationError("клиент в панели выключен")
                return c
        raise PanelClientVerificationError(
            "клиент после создания не найден в inbound (email/uuid не совпали)"
        )

    def build_vless_share_link(
        self,
        inbound_row: dict[str, Any],
        *,
        client_uuid: str,
        client_flow: str | None,
        remark: str,
    ) -> str:
        """Собрать vless:// по streamSettings inbound (как в 3x-ui). Только protocol=vless."""
        proto = str(inbound_row.get("protocol") or "").lower()
        if proto != "vless":
            raise PanelShareLinkError(f"inbound не VLESS ({proto!r}), прямой ключ не строим")

        stream_raw = inbound_row.get("streamSettings")
        if not isinstance(stream_raw, str) or not stream_raw.strip():
            raise PanelShareLinkError("у inbound нет streamSettings")

        try:
            stream = json.loads(stream_raw)
        except json.JSONDecodeError as e:
            raise PanelShareLinkError(f"streamSettings не JSON: {e}") from e
        if not isinstance(stream, dict):
            raise PanelShareLinkError("streamSettings должен быть объектом JSON")

        settings_obj: dict[str, Any] = {}
        settings_raw = inbound_row.get("settings")
        if isinstance(settings_raw, str) and settings_raw.strip():
            try:
                parsed = json.loads(settings_raw)
                if isinstance(parsed, dict):
                    settings_obj = parsed
            except json.JSONDecodeError:
                settings_obj = {}

        address = self._resolve_client_link_host(inbound_row)
        try:
            port_i = int(inbound_row.get("port"))
        except (TypeError, ValueError):
            raise PanelShareLinkError("некорректный port у inbound")

        flow = (client_flow or "").strip() or None
        try:
            return build_vless_share_url(
                stream=stream,
                inbound_settings=settings_obj,
                client_uuid=client_uuid,
                client_flow=flow,
                address=address,
                port=port_i,
                remark=remark or "",
            )
        except ValueError as e:
            raise PanelShareLinkError(str(e)) from e

    async def create_client(
        self,
        inbound_id: int,
        email: str,
        remark: str | None = None,
        telegram_user_id: int | None = None,
    ) -> CreatedClient:
        await self.login()
        sub_id = secrets.token_hex(8)
        client_uuid = str(uuid.uuid4())
        client_obj: dict[str, Any] = {
            "id": client_uuid,
            "email": email,
            "enable": True,
            "limitIp": 0,
            "totalGB": 0,
            "expiryTime": 0,
            "tgId": str(telegram_user_id) if telegram_user_id is not None else "",
            "subId": sub_id,
        }
        if remark:
            client_obj["remark"] = remark
        flow = (self._settings.panel_client_flow or "").strip()
        if flow:
            client_obj["flow"] = flow
        settings_payload = {"clients": [client_obj]}
        body = {"id": inbound_id, "settings": json.dumps(settings_payload)}
        raw = await self._request(
            "POST",
            self._settings.panel_api_add_client,
            json_body=body,
        )
        self._assert_success(raw, "add_client")
        log.info("panel_client_created", inbound_id=inbound_id, email=email)
        return CreatedClient(
            inbound_id=inbound_id,
            email=email,
            uuid=client_uuid,
            sub_id=sub_id,
        )

    async def delete_client_by_email(self, inbound_id: int, email: str) -> None:
        await self.login()
        body = {"id": inbound_id, "email": email}
        raw = await self._request(
            "POST",
            self._settings.panel_api_del_client,
            json_body=body,
        )
        self._assert_success(raw, "del_client")
        log.info("panel_client_deleted", inbound_id=inbound_id, email=email)

    async def update_client_remark(
        self,
        inbound_id: int,
        email: str,
        new_remark: str,
    ) -> None:
        """Optional; used only when PANEL_UPDATE_REMARK_ON_BIND is true.

        ASSUMPTION: ``PANEL_API_UPDATE_CLIENT`` accepts a similar body to addClient
        or panel-specific shape — this may require customization per version.
        """
        await self.login()
        body = {"id": inbound_id, "settings": json.dumps({"clients": [{"email": email, "remark": new_remark}]})}
        raw = await self._request(
            "POST",
            self._settings.panel_api_update_client,
            json_body=body,
        )
        self._assert_success(raw, "update_client")

    def build_subscription_link(self, sub_id: str | None, email: str, inbound_id: int) -> str:
        base = self._settings.subscription_public_base_url or self._settings.panel_base_url.rstrip("/")
        base = base.rstrip("/")
        if sub_id:
            return f"{base}/sub/{sub_id}"
        return f"{base}/sub/{email}?inbound={inbound_id}"
