import pytest
from pydantic import ValidationError

from routers.inserate_batch import InserateBatchRequest
from routers.inserate_by_url import InserateByUrlRequest
from utils.url_validation import is_kleinanzeigen_url, restrict_kleinanzeigen_route


@pytest.mark.parametrize(
    "url",
    [
        "https://kleinanzeigen.de/s-suche",
        "https://www.kleinanzeigen.de/s-suche",
        "https://img.kleinanzeigen.de/image.jpg",
        "https://www.kleinanzeigen.de:443/s-suche",
    ],
)
def test_kleinanzeigen_domain_and_https_are_allowed(url):
    assert is_kleinanzeigen_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://kleinanzeigen.de/s-suche",
        "https://kleinanzeigen.de.attacker.example/s-suche",
        "https://attacker-kleinanzeigen.de/s-suche",
        "https://evil.example/?next=kleinanzeigen.de",
        "https://user:pass@kleinanzeigen.de/s-suche",
        "https://kleinanzeigen.de:8443/s-suche",
        "file:///C:/Windows/win.ini",
        "https://kleinanzeigen.de:invalid/s-suche",
    ],
)
def test_non_kleinanzeigen_urls_are_rejected(url):
    assert not is_kleinanzeigen_url(url)
    with pytest.raises(ValueError):
        InserateByUrlRequest(url=url)


def test_url_endpoint_bounds_page_count():
    assert InserateByUrlRequest(url="https://www.kleinanzeigen.de", max_pages=50)
    with pytest.raises(ValidationError):
        InserateByUrlRequest(url="https://www.kleinanzeigen.de", max_pages=51)
    with pytest.raises(ValidationError):
        InserateByUrlRequest(url="https://www.kleinanzeigen.de", max_pages=0)


def test_batch_endpoint_bounds_fanout_and_concurrency():
    assert InserateBatchRequest(ids=["123"], max_concurrent=10)
    with pytest.raises(ValidationError):
        InserateBatchRequest(ids=["123"] * 101)
    with pytest.raises(ValidationError):
        InserateBatchRequest(ids=["123"], max_concurrent=11)
    with pytest.raises(ValidationError):
        InserateBatchRequest(ids=["123"], max_concurrent=0)
    with pytest.raises(ValidationError):
        InserateBatchRequest(ids=["x" * 33])


def test_direct_url_scraper_rejects_invalid_inputs_before_browser_access():
    from scrapers.inserate_by_url import scrape_by_url

    async def run_invalid_url():
        with pytest.raises(ValueError):
            await scrape_by_url(None, "https://example.com", max_pages=1)

    async def run_invalid_page_count():
        with pytest.raises(ValueError):
            await scrape_by_url(None, "https://www.kleinanzeigen.de", max_pages=51)

    import asyncio

    asyncio.run(run_invalid_url())
    asyncio.run(run_invalid_page_count())


class _FakeRequest:
    def __init__(self, url):
        self.url = url


class _FakeRoute:
    def __init__(self, url):
        self.request = _FakeRequest(url)
        self.action = None

    async def abort(self, reason=None):
        self.action = ("abort", reason)

    async def fallback(self):
        self.action = ("fallback", None)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.kleinanzeigen.de/s-suche", "fallback"),
        ("https://evil.example/redirect-target", "abort"),
        ("http://127.0.0.1:8000/admin", "abort"),
    ],
)
async def test_browser_route_blocks_non_kleinanzeigen_redirect_targets(url, expected):
    route = _FakeRoute(url)
    await restrict_kleinanzeigen_route(route)
    assert route.action[0] == expected
