"""Сборка vless:// по той же логике, что и 3x-ui web (Inbound.genVLESSLink).

Опирается на сырой JSON inbound: ``streamSettings`` и ``settings`` как в API
``GET /panel/api/inbounds/list``. Другие протоколы (VMess/Trojan/…) здесь не
строятся — см. ``ThreeXUiAdapter.build_vless_share_link``.

Версии 3x-ui могут слегка отличаться в именах полей; при сбое парсинга вызывающий
код получает ``PanelShareLinkError``.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote, urlencode


def _header_value(headers: Any, name: str) -> str:
    if not isinstance(headers, list):
        return ""
    for h in headers:
        if not isinstance(h, dict):
            continue
        if str(h.get("name") or "").lower() == name.lower():
            return str(h.get("value") or "")
    return ""


def _first_csv_or_list(val: Any) -> str | None:
    if val is None:
        return None
    if isinstance(val, str) and val.strip():
        return val.split(",")[0].strip()
    if isinstance(val, list) and val:
        return str(val[0]).strip()
    return None


def build_vless_share_url(
    *,
    stream: dict[str, Any],
    inbound_settings: dict[str, Any],
    client_uuid: str,
    client_flow: str | None,
    address: str,
    port: int,
    remark: str,
) -> str:
    uid = (client_uuid or "").strip()
    if not uid:
        raise ValueError("пустой UUID клиента")

    net = str(stream.get("network") or "tcp")
    security = str(stream.get("security") or "none")
    enc = inbound_settings.get("encryption")
    params: list[tuple[str, str]] = [
        ("type", net),
        ("encryption", str(enc if enc is not None else "none")),
    ]

    if net == "tcp":
        tcp = stream.get("tcpSettings") or {}
        header = tcp.get("header") or {}
        if header.get("type") == "http":
            req = header.get("request") or {}
            paths = req.get("path") or ["/"]
            if isinstance(paths, str):
                paths = [paths]
            params.append(("path", ",".join(str(p) for p in paths)))
            hv = _header_value(req.get("headers"), "host")
            if hv:
                params.append(("host", hv))
            params.append(("headerType", "http"))
    elif net == "ws":
        ws = stream.get("wsSettings") or {}
        params.append(("path", str(ws.get("path") or "/")))
        host = str(ws.get("host") or "").strip() or _header_value(ws.get("headers"), "host")
        if host:
            params.append(("host", host))
    elif net == "grpc":
        grpc = stream.get("grpcSettings") or {}
        if grpc.get("serviceName"):
            params.append(("serviceName", str(grpc["serviceName"])))
        if grpc.get("authority"):
            params.append(("authority", str(grpc["authority"])))
        if grpc.get("multiMode"):
            params.append(("mode", "multi"))
    elif net == "httpupgrade":
        hu = stream.get("httpupgradeSettings") or {}
        params.append(("path", str(hu.get("path") or "/")))
        host = str(hu.get("host") or "").strip() or _header_value(hu.get("headers"), "host")
        if host:
            params.append(("host", host))
    elif net == "xhttp":
        xh = stream.get("xhttpSettings") or {}
        params.append(("path", str(xh.get("path") or "/")))
        host = str(xh.get("host") or "").strip() or _header_value(xh.get("headers"), "host")
        if host:
            params.append(("host", host))
        if xh.get("mode"):
            params.append(("mode", str(xh["mode"])))

    flow_eff = (client_flow or "").strip()

    if security == "tls":
        tls = stream.get("tlsSettings") or {}
        params.append(("security", "tls"))
        st = tls.get("settings") or {}
        if isinstance(st, dict) and st.get("fingerprint"):
            params.append(("fp", str(st["fingerprint"])))
        alpn = tls.get("alpn")
        if alpn:
            if isinstance(alpn, list):
                params.append(("alpn", ",".join(str(x) for x in alpn)))
            else:
                params.append(("alpn", str(alpn)))
        if tls.get("serverName"):
            params.append(("sni", str(tls["serverName"])))
        ech = st.get("echConfigList") if isinstance(st, dict) else None
        if ech:
            params.append(("ech", json.dumps(ech) if not isinstance(ech, str) else str(ech)))
        if net == "tcp" and flow_eff:
            params.append(("flow", flow_eff))
    elif security == "reality":
        rel = stream.get("realitySettings") or {}
        st = rel.get("settings") or {}
        if not isinstance(st, dict):
            st = {}
        params.append(("security", "reality"))
        if st.get("publicKey"):
            params.append(("pbk", str(st["publicKey"])))
        if st.get("fingerprint"):
            params.append(("fp", str(st["fingerprint"])))
        sni = _first_csv_or_list(rel.get("serverNames"))
        if sni:
            params.append(("sni", sni))
        sid = _first_csv_or_list(rel.get("shortIds"))
        if sid:
            params.append(("sid", sid))
        if st.get("spiderX"):
            params.append(("spx", str(st["spiderX"])))
        if st.get("mldsa65Verify"):
            params.append(("pqv", str(st["mldsa65Verify"])))
        if net == "tcp" and flow_eff:
            params.append(("flow", flow_eff))
    else:
        params.append(("security", "none"))

    host_disp = address
    if ":" in address and not address.startswith("["):
        host_disp = f"[{address}]"
    base = f"vless://{uid}@{host_disp}:{int(port)}"
    query = urlencode(params)
    frag = quote(remark or "", safe="")
    return f"{base}?{query}#{frag}"
