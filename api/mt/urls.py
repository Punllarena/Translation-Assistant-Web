"""SSRF guard for user-supplied endpoint URLs (LibreTranslate / Ollama credentials).

The server defaults (TA_OLLAMA_URL, TA_LIBRETRANSLATE_URL) are operator-trusted and are
not checked. Blocking: call it off the event loop (it resolves DNS).
"""

import ipaddress
import socket
from urllib.parse import urlsplit


def _blocked(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])  # drop an IPv6 scope id
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_unspecified
            or ip.is_reserved or ip.is_multicast)


def check_user_url(url: str, allow_private: bool, label: str) -> str | None:
    """An error message for a URL the server must not call, else None.

    ponytail: DNS is checked here, at prepare time, not pinned for the request that
    follows, so a rebinding host has a short window; pin the address if that matters.
    """
    try:
        parts = urlsplit(url)
        scheme, host, port = parts.scheme, parts.hostname, parts.port
    except ValueError:  # e.g. "http://[::1" or a port out of range
        scheme = host = port = None
    if scheme not in ("http", "https") or not host:
        return f"That {label} URL is not a valid http(s) address."
    if allow_private:
        return None
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        return f"That {label} URL's host could not be resolved."
    if any(_blocked(info[4][0]) for info in infos):
        return (f"That {label} URL points at a private or local address, "
                "which this server does not allow.")
    return None
