import socket

import pytest

from api.mt import urls


@pytest.fixture
def resolves(monkeypatch):
    def install(*addresses):
        def fake(host, *args, **kwargs):
            if not addresses:
                raise socket.gaierror("no such host")
            return [(socket.AF_INET6 if ":" in a else socket.AF_INET, socket.SOCK_STREAM, 6,
                     "", (a, 0)) for a in addresses]
        monkeypatch.setattr(urls.socket, "getaddrinfo", fake)
    return install


@pytest.mark.parametrize("address", ["93.184.216.34", "2606:2800:220:1::1"])
def test_public_address_passes(resolves, address):
    resolves(address)
    assert urls.check_user_url("https://lt.example.com/x", False, "LibreTranslate") is None


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254",
                                     "0.0.0.0", "100.64.0.1", "::1", "fe80::1", "::ffff:127.0.0.1",
                                     "224.0.0.1"])
def test_private_or_local_address_is_refused(resolves, address):
    resolves(address)
    msg = urls.check_user_url("http://lt.example.com", False, "LibreTranslate")
    assert msg == ("That LibreTranslate URL points at a private or local address, "
                   "which this server does not allow.")


def test_any_private_address_among_several_is_refused(resolves):
    resolves("93.184.216.34", "10.0.0.1")
    assert urls.check_user_url("http://lt.example.com", False, "Ollama") is not None


def test_allow_private_skips_the_address_check(resolves):
    resolves("127.0.0.1")
    assert urls.check_user_url("http://localhost:11434", True, "Ollama") is None


@pytest.mark.parametrize("url", ["ftp://host/x", "file:///etc/passwd", "http://", "nonsense",
                                 "http://[::1", "http://h:99999"])
def test_non_http_urls_are_refused(resolves, url):
    resolves("93.184.216.34")
    assert "valid http" in urls.check_user_url(url, True, "Ollama")


def test_unresolvable_host_is_refused(resolves):
    resolves()
    assert "could not be resolved" in urls.check_user_url("http://nowhere", False, "Ollama")


@pytest.mark.parametrize("url", [
    "http://169.254.169.254/latest", "http://[fe80::1]:11434", "http://0.0.0.0:11434",
    "http://[::]:11434", "http://metadata.google.internal/", "http://Metadata.Google.Internal./",
])
def test_metadata_and_link_local_refused_even_when_private_allowed(url):
    assert "link-local or metadata" in urls.check_user_url(url, True, "Ollama")


def test_mapped_link_local_refused_when_private_allowed(resolves):
    resolves("::ffff:169.254.169.254")
    assert urls.check_user_url("http://h.example", True, "Ollama") is not None


def test_lan_address_allowed_when_private_allowed():
    assert urls.check_user_url("http://192.168.1.20:11434", True, "Ollama") is None
