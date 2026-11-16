from datetime import datetime
from types import SimpleNamespace

from scrapers.inserate_ultra_optimized import UltraOptimizedScraper
from utils.performance import PageMetrics


class _FakeBrowserManager:
    _semaphore = SimpleNamespace(_value=2)

    @staticmethod
    def get_performance_metrics():
        return {"contexts_in_use": 0, "contexts_in_pool": 0}


async def test_date_cutoff_does_not_dispatch_or_include_later_pages(monkeypatch):
    scraper = UltraOptimizedScraper(_FakeBrowserManager())
    requested_pages = []
    dates = {
        1: "2026-01-10T00:00:00",
        2: "2024-12-31T00:00:00",
        3: "2026-02-01T00:00:00",
    }

    async def fake_fetch(url, page_num, extra_selectors=None):
        requested_pages.append(page_num)
        return (
            [
                {
                    "adid": str(page_num),
                    "title": f"page {page_num}",
                    "published_at": dates[page_num],
                    "is_top_ad": False,
                }
            ],
            PageMetrics(
                page_number=page_num,
                url=url,
                start_time=0.0,
                end_time=0.1,
                success=True,
                retry_count=0,
                results_count=1,
            ),
            {},
        )

    monkeypatch.setattr(scraper, "ultra_optimized_fetch_page", fake_fetch)
    result = await scraper.ultra_optimized_scrape(
        query="test",
        page_count=3,
        min_publish_date=datetime(2025, 1, 1),
    )

    assert requested_pages == [1, 2]
    assert [item["adid"] for item in result["results"]] == ["1"]
    assert result["pages_fetched"] == 2
    await scraper.cleanup()
