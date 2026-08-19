from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx


class HttpConnectorError(RuntimeError):
    pass


@dataclass(slots=True)
class HttpResult:
    status_code: int
    headers: dict[str, str]
    data: object


def _is_forbidden_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return (
        ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_unspecified
    )


def validate_target(url: str, *, allow_private: bool = False) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HttpConnectorError("only http/https URLs with a host are allowed")
    if parsed.username or parsed.password:
        raise HttpConnectorError("URL userinfo is not allowed")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "metadata.google.internal", "instance-data"} and not allow_private:
        raise HttpConnectorError("private or metadata host is not allowed")
    try:
        direct_ip = ipaddress.ip_address(host)
    except ValueError:
        direct_ip = None
    if direct_ip and _is_forbidden_ip(str(direct_ip)) and not allow_private:
        raise HttpConnectorError("private network target is not allowed")
    if not direct_ip:
        try:
            addresses = {
                item[4][0]
                for item in socket.getaddrinfo(host, parsed.port, type=socket.SOCK_STREAM)
            }
        except OSError as exc:
            raise HttpConnectorError("could not resolve connector host") from exc
        if any(_is_forbidden_ip(address) for address in addresses) and not allow_private:
            raise HttpConnectorError("connector host resolves to a private address")
    return url


async def invoke(
    *,
    base_url: str,
    path: str = "",
    method: str = "GET",
    headers: dict[str, str] | None = None,
    params: dict[str, object] | None = None,
    json_body: object | None = None,
    allow_private: bool = False,
    timeout: float = 60.0,
    max_response_bytes: int = 10 * 1024 * 1024,
    transport: httpx.AsyncBaseTransport | None = None,
) -> HttpResult:
    url = validate_target(
        urljoin(base_url.rstrip("/") + "/", path.lstrip("/")), allow_private=allow_private
    )
    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=False, transport=transport
    ) as client:
        response = await client.request(
            method.upper(), url, headers=headers, params=params, json=json_body
        )
        content = await response.aread()
    if len(content) > max_response_bytes:
        raise HttpConnectorError("connector response exceeded configured size limit")
    try:
        data: object = response.json()
    except ValueError:
        data = content.decode("utf-8", errors="replace")
    return HttpResult(status_code=response.status_code, headers=dict(response.headers), data=data)


__all__ = ["HttpConnectorError", "HttpResult", "invoke", "validate_target"]
