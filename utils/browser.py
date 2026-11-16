import asyncio
import os

from playwright.async_api import BrowserContext, Page, Route, async_playwright

from utils.user_agent import get_random_ua

# External CDP endpoint (e.g. BrowserUse cloud session, browserless, plain
# chromium --remote-debugging-port). When set, the app connects to that
# browser instead of launching a local bundled Chromium.
CDP_URL = os.environ.get("BROWSER_CDP_URL", "").strip() or None

# Resource types that never affect extraction: the scraper reads the DOM via
# query_selector/evaluate/inner_text only, so images, media and fonts can be
# aborted before they cost bandwidth and CPU.
#
# Stylesheets must NOT be blocked: inner_text() honours CSS visibility, and
# ad pages carry CSS-hidden markers such as
# `<span class="pvap-reserved-title is-hidden">Reserviert • </span>` inside
# #viewad-title. Without CSS those leak into the text and every ad is
# reported as reserved.
BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}

# Ad-tech / consent / promo script paths. Kleinanzeigen serves these from
# first-party URLs, so they can't be caught by domain blocklists. None of
# them contribute to .ad-listitem extraction (listings are SSR'd Astro
# islands); blocking them removes ~1.4MB of JS per page load.
BLOCKED_URL_PATTERNS = (
    "/liberty/",  # ad platform: renderer, prebid, liberty.min.js
    "/gdpr/",  # consent-management-platform banner
    "promotion-frontend",  # promo bundle
    "kameleoon",  # A/B testing
    "sgtm-legacy",  # Google Tag Manager
)


async def _block_heavy_resources(route: Route):
    request = route.request
    url = request.url
    if request.resource_type in BLOCKED_RESOURCE_TYPES or any(
        p in url for p in BLOCKED_URL_PATTERNS
    ):
        await route.abort()
    else:
        await route.continue_()


# Set BROWSER_DISABLE_RESOURCE_BLOCKING=1 to turn off request interception
# entirely (useful for debugging extraction issues or A/B benchmarking).
# Read at context-creation time so tests and benchmarks can toggle per-run.
def _resource_blocking_disabled() -> bool:
    return os.environ.get("BROWSER_DISABLE_RESOURCE_BLOCKING", "").strip() == "1"


async def _new_context(browser, user_agent: str) -> BrowserContext:
    """Create a context with heavy subresources blocked at the routing layer."""
    context = await browser.new_context(user_agent=user_agent)
    if not _resource_blocking_disabled():
        await context.route("**/*", _block_heavy_resources)
    return context


class PlaywrightManager:
    def __init__(self):
        self._playwright = None
        self._browser = None

    async def start(self):
        self._playwright = await async_playwright().start()
        if CDP_URL:
            self._browser = await self._playwright.chromium.connect_over_cdp(CDP_URL)
        else:
            self._browser = await self._playwright.chromium.launch(headless=True)

    async def new_context_page(self):
        context = await _new_context(self._browser, get_random_ua())
        return await context.new_page()

    async def close_page(self, page):
        await page.close()

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()


class OptimizedPlaywrightManager:
    def __init__(self, max_contexts: int = 10, max_concurrent: int = 5):
        self._playwright = None
        self._browser = None
        self._context_pool: list[BrowserContext] = []
        self._context_in_use: list[BrowserContext] = []
        self._max_contexts = max_contexts
        self._semaphore = asyncio.Semaphore(max_concurrent)
        if max_contexts < 1 or max_concurrent < 1:
            raise ValueError("max_contexts and max_concurrent must be positive")
        self._context_condition = asyncio.Condition()

        # Performance metrics
        self._contexts_created = 0
        self._contexts_reused = 0
        self._concurrent_operations = 0
        self._max_concurrent_reached = 0

    async def start(self):
        """Initialize the browser and create initial context pool"""
        self._playwright = await async_playwright().start()
        if CDP_URL:
            self._browser = await self._playwright.chromium.connect_over_cdp(CDP_URL)
        else:
            self._browser = await self._playwright.chromium.launch(headless=True)

        # Pre-create some contexts for the pool
        initial_contexts = min(3, self._max_contexts)
        if not CDP_URL:  # skip pre-warm against external/ephemeral browsers
            for _ in range(initial_contexts):
                context = await _new_context(self._browser, get_random_ua())
                self._context_pool.append(context)
                self._contexts_created += 1

    async def get_context(self) -> BrowserContext:
        """Get a pooled context or wait without holding the pool lock."""
        async with self._context_condition:
            while (
                not self._context_pool
                and len(self._context_in_use) >= self._max_contexts
            ):
                await self._context_condition.wait()

            if self._context_pool:
                context = self._context_pool.pop()
                self._context_in_use.append(context)
                self._contexts_reused += 1
                return context

            context = await _new_context(self._browser, get_random_ua())
            self._context_in_use.append(context)
            self._contexts_created += 1
            return context

    async def release_context(self, context: BrowserContext):
        """Clean a context and return it to the pool, waking waiting callers."""
        async with self._context_condition:
            if context not in self._context_in_use:
                return

            self._context_in_use.remove(context)
            try:
                for page in context.pages:
                    await page.close()
                await context.clear_cookies()

                if len(self._context_pool) < self._max_contexts // 2:
                    self._context_pool.append(context)
                else:
                    await context.close()

            except Exception:
                # A context that cannot be cleaned is unsafe to reuse; close it
                # instead, but always wake callers waiting for a pool slot.
                try:
                    await context.close()
                except Exception:
                    pass
                raise
            finally:
                self._context_condition.notify_all()

    async def execute_with_semaphore(self, coro):
        """Execute a coroutine with concurrency control"""
        async with self._semaphore:
            self._concurrent_operations += 1
            self._max_concurrent_reached = max(
                self._max_concurrent_reached, self._concurrent_operations
            )
            try:
                result = await coro
                return result
            finally:
                self._concurrent_operations -= 1

    async def new_context_page(self) -> Page:
        """Create a new page using context pooling (backward compatibility)"""
        context = await self.get_context()
        page = await context.new_page()
        # Store context reference on page for cleanup
        page._context_ref = context
        return page

    async def close_page(self, page: Page):
        """Close a page and return its context to the pool"""
        context = getattr(page, "_context_ref", None)
        await page.close()
        if context:
            await self.release_context(context)

    def get_performance_metrics(self) -> dict:
        """Get current performance metrics"""
        return {
            "contexts_created": self._contexts_created,
            "contexts_reused": self._contexts_reused,
            "contexts_in_pool": len(self._context_pool),
            "contexts_in_use": len(self._context_in_use),
            "max_contexts": self._max_contexts,
            "max_concurrent_reached": self._max_concurrent_reached,
            "current_concurrent": self._concurrent_operations,
            "reuse_ratio": self._contexts_reused / max(self._contexts_created, 1),
        }

    async def close(self):
        """Clean up all resources"""
        # Close all contexts in pool
        for context in self._context_pool:
            await context.close()

        # Close all contexts in use
        for context in self._context_in_use:
            await context.close()

        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

        self._context_pool.clear()
        self._context_in_use.clear()
