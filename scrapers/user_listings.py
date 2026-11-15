"""Scrape every public listing on a Kleinanzeigen user's inventory page."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, TYPE_CHECKING
from urllib.parse import urlencode, urljoin

if TYPE_CHECKING:
    from utils.browser import OptimizedPlaywrightManager

BASE_URL = "https://www.kleinanzeigen.de"
_PAGE_LIMIT = 1000  # Guard against a broken/looping pagination link.


def user_inventory_url(user_id: str, page_num: int = 1) -> str:
    """Build a public inventory URL, retaining the site's usual date sort."""
    if not user_id.isdigit():
        raise ValueError("user_id must contain only digits")
    if page_num < 1:
        raise ValueError("page_num must be at least 1")
    query = {"userId": user_id, "sortingField": "SORTING_DATE"}
    if page_num > 1:
        query["pageNum"] = str(page_num)
    return f"{BASE_URL}/s-bestandsliste.html?{urlencode(query)}"


async def scrape_user_listings(
    browser_manager: OptimizedPlaywrightManager, user_id: str
) -> Dict[str, Any]:
    """Fetch sequential pages until Kleinanzeigen provides no next-page link."""
    base_url = user_inventory_url(user_id)
    from scrapers.inserate_ultra_optimized import create_ultra_optimized_scraper

    scraper = await create_ultra_optimized_scraper(browser_manager)
    context = await browser_manager.get_context()
    page = None
    all_results: List[Dict[str, Any]] = []
    seen_ids = set()
    pages_fetched = 0
    current_url = base_url

    try:
        page = await context.new_page()
        for _ in range(_PAGE_LIMIT):
            await page.goto(current_url, wait_until="domcontentloaded", timeout=120000)
            pages_fetched += 1
            page_results = await scraper.extract_ads_optimized(page)
            for listing in page_results:
                listing_id = listing.get("adid")
                if listing_id and listing_id not in seen_ids:
                    seen_ids.add(listing_id)
                    all_results.append(listing)

            next_link = page.locator(".pagination-next[href]").first
            if await next_link.count() == 0:
                break
            next_href = await next_link.get_attribute("href")
            if not next_href:
                break
            next_url = urljoin(BASE_URL, next_href)
            if next_url == current_url:
                break
            current_url = next_url
            await asyncio.sleep(2)
        else:
            raise RuntimeError(f"Pagination exceeded safety limit of {_PAGE_LIMIT} pages")

        return {
            "success": True,
            "user_id": user_id,
            "results": all_results,
            "unique_results": len(all_results),
            "pages_fetched": pages_fetched,
        }
    finally:
        if page:
            await page.close()
        await browser_manager.release_context(context)
        await scraper.cleanup()
