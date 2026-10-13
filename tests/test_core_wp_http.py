import json

import httpx
import pytest

from api.core import wp_http
from api.core.wp import WPPublishError

SITE = "https://blog.example.com"


def make(handler):
    return wp_http.client(transport=httpx.MockTransport(handler))


def test_publish_posts_json_to_the_normalized_endpoint():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"created": True, "post_url": f"{SITE}/p/1"})

    with make(handler) as c:
        out = wp_http.publish(c, SITE + "/", {"a": 1})
        assert out == {"created": True, "post_url": f"{SITE}/p/1"}
    assert str(seen[0].url) == SITE + "/wp-json/ta-publisher/v1/publish"
    assert json.loads(seen[0].content) == {"a": 1}


def test_publish_409_is_a_result():
    with make(lambda r: httpx.Response(409, json={"created": False, "page_url": "x"})) as c:
        assert wp_http.publish(c, SITE, {}) == {"created": False, "page_url": "x"}
    with make(lambda r: httpx.Response(409, text="<html>")) as c:
        assert wp_http.publish(c, SITE, {}) == {"created": False}


def test_plugin_error_key_is_the_message():
    with make(lambda r: httpx.Response(500, json={"error": "Failed to create page"})) as c:
        with pytest.raises(WPPublishError) as e:
            wp_http.publish(c, SITE, {})
    assert e.value.message == "Failed to create page" and e.value.status_code == 500


def test_non_json_success_is_an_error():
    with make(lambda r: httpx.Response(200, text="<html>maintenance</html>")) as c:
        with pytest.raises(WPPublishError, match="non-JSON"):
            wp_http.publish(c, SITE, {})


def test_redirects_are_not_followed():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})

    with make(handler) as c:
        with pytest.raises(WPPublishError, match="127.0.0.1/admin"):
            wp_http.publish(c, SITE, {})
    assert len(calls) == 1


def test_connection_error_names_the_url_but_not_the_key():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    with make(handler) as c:
        with pytest.raises(WPPublishError) as e:
            wp_http.check_status(c, SITE, "sekret-key", "slug", 3)
    assert SITE in e.value.message and "sekret-key" not in e.value.message
    assert e.value.status_code is None


def test_check_status_sends_key_slug_and_chapter_to_the_site_root():
    seen = []

    def handler(request):
        seen.append(request.url)
        return httpx.Response(200, json={"status": "publish", "post_url": "u"})

    with make(handler) as c:
        out = wp_http.check_status(c, SITE + "/wp-json/ta-publisher/v1/publish", "k", "s", 2)
    assert out == {"status": "publish", "post_url": "u"}
    assert seen[0].path == "/wp-json/ta-publisher/v1/status"
    assert dict(seen[0].params) == {"api_key": "k", "series_slug": "s", "chapter": "2"}


def test_check_status_401():
    with make(lambda r: httpx.Response(401, json={"error": "Invalid API key"})) as c:
        with pytest.raises(WPPublishError) as e:
            wp_http.check_status(c, SITE, "k", "s", 1)
    assert (e.value.message, e.value.status_code) == ("Invalid API key", 401)


def test_publish_illustrations_posts_to_the_illustrations_route():
    seen = []

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, json={"created": True, "page_url": "g"})

    with make(handler) as c:
        out = wp_http.publish_illustrations(c, SITE + "/wp-json/ta-publisher/v1/publish", {})
        assert out["page_url"] == "g"
    assert seen == ["/wp-json/ta-publisher/v1/illustrations"]


def test_a_json_list_body_is_an_error_not_a_crash():
    with make(lambda r: httpx.Response(200, json=[1, 2])) as c:
        with pytest.raises(WPPublishError):
            wp_http.publish(c, SITE, {})
