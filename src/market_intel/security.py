from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from .config import get_settings


def detect_prompt_injection(text: str) -> list[str]:
    cfg = get_settings().section("security")
    lowered = text.lower()
    return [marker for marker in cfg["prompt_injection_markers"] if marker.lower() in lowered]


def _is_blocked_ip(ip: str) -> bool:
    cfg = get_settings().section("security")
    address = ipaddress.ip_address(ip)
    return any(address in ipaddress.ip_network(net) for net in cfg["blocked_ip_networks"])


def validate_public_url(url: str) -> str:
    cfg = get_settings().section("security")
    parsed = urlparse(url.strip())
    if parsed.scheme not in cfg["allowed_schemes"]:
        raise ValueError("Only configured HTTP/HTTPS schemes are allowed.")
    if not parsed.hostname:
        raise ValueError("URL has no valid hostname.")
    hostname = parsed.hostname.lower()
    if hostname in {h.lower() for h in cfg["blocked_hostnames"]}:
        raise ValueError("Local/private hostnames are blocked.")
    try:
        infos = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ValueError(f"Unable to resolve hostname: {hostname}") from exc
    for info in infos:
        ip = info[4][0]
        if _is_blocked_ip(ip):
            raise ValueError("URL resolves to a private/local network address and is blocked.")
    return url.strip()
