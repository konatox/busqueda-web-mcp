"""Validate all DNS answers and pin requests to a validated public address."""

import asyncio
import ipaddress
import socket
from dataclasses import dataclass

import httpx

from . import config


class UnsafeURL(ValueError):
    pass


@dataclass(frozen=True)
class Target:
    url: httpx.URL
    address: str
    addresses: tuple[str, ...] = ()

    @property
    def connect_url(self) -> httpx.URL:
        return self.url.copy_with(host=self.address)

    @property
    def host_header(self) -> str:
        return self.url.netloc.decode("ascii")


def public_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    # Mapped IPv4 and transition mechanisms can bypass plain IPv6 checks.
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return public_ip(str(ip.ipv4_mapped))
        if ip.sixtofour is not None or ip.teredo is not None:
            return False
        if ip in ipaddress.ip_network("64:ff9b::/96") or ip in ipaddress.ip_network("64:ff9b:1::/48"):
            return False
    return ip.is_global and not ip.is_multicast and not ip.is_reserved


def parse_url(url: str) -> httpx.URL:
    if not isinstance(url, str) or not url or len(url) > config.MAX_URL_CHARS:
        raise UnsafeURL("URL is empty or too long")
    if any(ord(c) <= 32 or ord(c) == 127 for c in url) or "\\" in url:
        raise UnsafeURL("URL contains invalid characters")
    try:
        parsed = httpx.URL(url)
        if parsed.scheme not in {"http", "https"} or not parsed.host:
            raise UnsafeURL("Only public HTTP and HTTPS URLs are allowed")
        if parsed.username or parsed.password:
            raise UnsafeURL("URLs with credentials are not allowed")
        host = parsed.host.lower().rstrip(".")
        if "%" in host or host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            raise UnsafeURL("Local and internal hosts are blocked")
        if host in {"metadata.google.internal", "metadata", "instance-data", "instance-data.ec2.internal"}:
            raise UnsafeURL("Cloud metadata endpoints are blocked")
        _ = parsed.port
        return parsed.copy_with(fragment=None)
    except (httpx.InvalidURL, ValueError) as exc:
        if isinstance(exc, UnsafeURL):
            raise
        raise UnsafeURL("Invalid URL") from exc


async def resolve_target(url: str) -> Target:
    parsed = parse_url(url)
    try:
        literal = ipaddress.ip_address(parsed.host)
    except ValueError:
        try:
            answers = await asyncio.wait_for(
                asyncio.to_thread(socket.getaddrinfo, parsed.host, parsed.port or (443 if parsed.scheme == "https" else 80),
                                  type=socket.SOCK_STREAM),
                timeout=config.REQUEST_TIMEOUT,
            )
        except socket.gaierror as exc:
            raise ValueError("Could not resolve hostname") from exc
        addresses = list(dict.fromkeys(answer[4][0] for answer in answers))
    else:
        addresses = [str(literal)]
    if not addresses or any(not public_ip(address) for address in addresses):
        raise UnsafeURL("URL resolves to a private, local or reserved address")
    return Target(parsed, addresses[0], tuple(addresses))
