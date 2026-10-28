"""WordPress HTTP calls, from the desktop translation_assistant/wp_publisher.py
(check_status, publish, publish_illustrations), over an injected httpx.Client instead
of urllib so tests use MockTransport (spec §12)."""

import httpx

from api.core.wp import WPPublishError, normalize_endpoint_url, site_base

STATUS_PATH = "/wp-json/ta-publisher/v1/status"
ILLUSTRATIONS_PATH = "/wp-json/ta-publisher/v1/illustrations"


def client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    # No redirects: every hop would need the SSRF check again, and the body carries the
    # API key. The error names the Location so the user can save that address instead.
    return httpx.Client(transport=transport, follow_redirects=False, timeout=15)


def _message(r: httpx.Response) -> str:
    try:
        body = r.json()
    except ValueError:
        body = None
    if isinstance(body, dict) and (body.get("error") or body.get("message")):
        return str(body.get("error") or body.get("message"))
    return f"HTTP {r.status_code} {r.reason_phrase}"


def _send(c: httpx.Client, method: str, url: str, *, timeout: float,
          ok_409: bool = False, **kwargs) -> dict:
    """``url`` carries no query string, so it is safe to show (the status key is in params)."""
    try:
        r = c.request(method, url, timeout=timeout, **kwargs)
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        raise WPPublishError(f"Could not reach {url}: {type(exc).__name__}") from None
    if r.is_redirect:
        raise WPPublishError(
            f"{url} redirected to {r.headers.get('location', '?')}; save that address instead",
            r.status_code,
        )
    if ok_409 and r.status_code == 409:  # the desktop read a 409 as "already there"
        try:
            body = r.json()
        except ValueError:
            body = None
        return body if isinstance(body, dict) else {"created": False}
    if r.is_error:
        raise WPPublishError(_message(r), r.status_code)
    try:
        body = r.json()
    except ValueError:
        raise WPPublishError(f"Server returned non-JSON response (HTTP {r.status_code})") from None
    if not isinstance(body, dict):
        raise WPPublishError("Server returned an unexpected response")
    return body


def check_status(c: httpx.Client, endpoint_url: str, api_key: str, series_slug: str,
                 chapter: int) -> dict:
    params = {"api_key": api_key, "series_slug": series_slug, "chapter": chapter}
    return _send(c, "GET", site_base(endpoint_url) + STATUS_PATH, params=params, timeout=10)


def check_illustrations_status(c: httpx.Client, endpoint_url: str, api_key: str,
                               series_slug: str, volume_title: str) -> dict:
    """The illustrations form of /status: the gallery is named by its volume, and the
    plugin answers 400 when ``chapter`` is sent too."""
    params = {"api_key": api_key, "series_slug": series_slug, "illustrations": 1,
              "volume_title": volume_title}
    return _send(c, "GET", site_base(endpoint_url) + STATUS_PATH, params=params, timeout=10)


def publish(c: httpx.Client, endpoint_url: str, payload: dict) -> dict:
    return _send(c, "POST", normalize_endpoint_url(endpoint_url), json=payload,
                 timeout=15, ok_409=True)


def publish_illustrations(c: httpx.Client, endpoint_url: str, payload: dict) -> dict:
    return _send(c, "POST", site_base(endpoint_url) + ILLUSTRATIONS_PATH, json=payload,
                 timeout=60)
