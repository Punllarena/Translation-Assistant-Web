"""SSRF guard for user-supplied endpoint URLs (Ollama and LibreTranslate credentials, WordPress).

Ollama endpoints come from users and are always checked; LibreTranslate's operator default
(TA_LIBRETRANSLATE_URL) is operator-trusted and is not. With private addresses allowed, link-local
(cloud metadata) and unspecified addresses are still refused. Blocking: call it off the event loop
(it resolves DNS).
"""

import ipaddress
import socket
from urllib.parse import urlsplit

_METADATA_MESSAGE = ("That {label} URL points at a link-local or metadata address, "
                     "which is never allowed.")


def _blocked(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])  # drop an IPv6 scope id
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    # not is_global also covers shared space such as 100.64.0.0/10 (CGNAT, Tailscale).
    return (not ip.is_global or ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_unspecified or ip.is_reserved or ip.is_multicast)


def _never_allowed(address: str) -> bool:
    """Link-local (cloud metadata) and unspecified addresses: never allowed."""
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_link_local or ip.is_unspecified


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
    if allow_private and host.lower().rstrip(".") == "metadata.google.internal":
        return _METADATA_MESSAGE.format(label=label)  # refused by name: it may not resolve here
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        if allow_private:
            return None  # the request itself will fail to connect
        return f"That {label} URL's host could not be resolved."
    if allow_private:
        if any(_never_allowed(info[4][0]) for info in infos):
            return _METADATA_MESSAGE.format(label=label)
        return None
    if any(_blocked(info[4][0]) for info in infos):
        return (f"That {label} URL points at a private or local address, "
                "which this server does not allow.")
    return None
