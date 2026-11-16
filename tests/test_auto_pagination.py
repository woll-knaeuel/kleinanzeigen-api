from types import SimpleNamespace

from scrapers.inserate_ultra_optimized import UltraOptimizedScraper
from utils.performance import PageMetrics


class _FakeBrowserManager:
    _semaphore = SimpleNamespace(_value=1)

    @staticmethod
    def get_performance_metrics():
        return {"contexts_in_use": 0, "contexts_in_pool": 0}


async def test_omitted_page_count_uses_automatic_pagination(monkeypatch):
    scraper = UltraOptimizedScraper(_FakeBrowserManager())
    requested_urls = []

    async def fake_fetch(url, page_num, extra_selectors=None):
        requested_urls.append(url)
        return (
            [],
            PageMetrics(
                page_number=page_num,
                url=url,
                start_time=0.0,
                end_time=0.1,
                success=True,
                retry_count=0,
            ),
            {"breadcrump_summary": "1 - 1 von 1"},
        )

    monkeypatch.setattr(scraper, "ultra_optimized_fetch_page", fake_fetch)
    result = await scraper.ultra_optimized_scrape(query="fahrrad", page_count=None)

    assert result["pages_fetched"] == 1
    assert len(requested_urls) == 1


def test_page_count_is_optional_in_openapi():
    from main import app

    parameter = next(
        parameter
        for parameter in app.openapi()["paths"]["/inserate"]["get"]["parameters"]
        if parameter["name"] == "page_count"
    )
    assert parameter["required"] is False


async def test_inserate_route_passes_none_when_page_count_is_omitted(monkeypatch):
    from routers import inserate_ultra

    async def fake_scrape(**kwargs):
        assert kwargs["page_count"] is None
        return {
            "success": True,
            "results": [],
            "unique_results": 0,
            "time_taken": 0.1,
            "performance_metrics": {
                "pages_requested": 1,
                "pages_successful": 1,
                "success_rate": 100,
                "average_page_time": 0.1,
            },
        }

    monkeypatch.setattr(inserate_ultra, "ultra_optimized_scrape_inserate", fake_scrape)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(browser_manager=object()))
    )
    result = await inserate_ultra.get_inserate_ultra_optimized(
        request=request,
        query=None,
        location=None,
        radius=None,
        min_price=None,
        max_price=None,
        category_id=None,
        category_slug=None,
        page=1,
        page_count=None,
        min_publish_date=None,
        include_terms=None,
        exclude_terms=None,
        use_regex=False,
        match_all_include=False,
        case_sensitive=False,
        filter_fields="title,description",
    )

    assert result["success"] is True


async def test_category_query_survives_pagination(monkeypatch):
    scraper = UltraOptimizedScraper(_FakeBrowserManager())
    requested_urls = []

    async def fake_fetch(url, page_num, extra_selectors=None):
        requested_urls.append(url)
        return (
            [{"adid": str(page_num), "title": "liebherr"}],
            PageMetrics(
                page_number=page_num,
                url=url,
                start_time=0.0,
                end_time=0.1,
                success=True,
                retry_count=0,
                results_count=1,
            ),
            {"breadcrump_summary": "1 - 25 von 26"} if page_num == 1 else {},
        )

    monkeypatch.setattr(scraper, "ultra_optimized_fetch_page", fake_fetch)
    result = await scraper.ultra_optimized_scrape(
        query="liebherr",
        category_id=161,
        category_slug="s-multimedia-elektronik",
        page_count=2,
    )

    assert requested_urls == [
        "https://www.kleinanzeigen.de/s-multimedia-elektronik/liebherr/k0c161",
        "https://www.kleinanzeigen.de/s-multimedia-elektronik/seite:2/liebherr/k0c161",
    ]
    assert result["pages_fetched"] == 2
