"""Tests for SSRF guards on the recipe fetcher.

These exercise the pure IP classification and the URL validator against literal
IPs / localhost, so they run offline (no outbound DNS or HTTP).
"""
import pytest

from app.services.scraper import ScrapeError, _is_blocked_ip, _validate_public_url


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",         # loopback
        "169.254.169.254",   # link-local (cloud metadata)
        "10.0.0.1",          # private
        "172.16.5.4",        # private
        "192.168.1.1",       # private
        "0.0.0.0",           # unspecified  # noqa: S104
        "::1",               # loopback (v6)
        "fe80::1",           # link-local (v6)
        "fd00::1",           # unique-local (v6, private)
        "not-an-ip",         # unparseable -> blocked
    ],
)
def test_is_blocked_ip_rejects_non_public(ip):
    assert _is_blocked_ip(ip) is True


@pytest.mark.parametrize("ip", ["8.8.8.8", "1.1.1.1", "2606:4700:4700::1111"])
def test_is_blocked_ip_allows_public(ip):
    assert _is_blocked_ip(ip) is False


def test_validate_public_url_blocks_metadata_endpoint():
    with pytest.raises(ScrapeError):
        _validate_public_url("http://169.254.169.254/latest/meta-data/")


def test_validate_public_url_blocks_loopback():
    with pytest.raises(ScrapeError):
        _validate_public_url("http://127.0.0.1:8000/")


def test_validate_public_url_blocks_localhost():
    with pytest.raises(ScrapeError):
        _validate_public_url("http://localhost/admin")


def test_validate_public_url_blocks_non_http_scheme():
    with pytest.raises(ScrapeError):
        _validate_public_url("file:///etc/passwd")


def test_validate_public_url_blocks_private_range():
    with pytest.raises(ScrapeError):
        _validate_public_url("http://192.168.1.1/")
