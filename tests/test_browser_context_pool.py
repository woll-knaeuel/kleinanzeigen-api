import asyncio

import pytest

from utils.browser import OptimizedPlaywrightManager


class _FakePage:
    async def close(self):
        return None


class _FakeContext:
    def __init__(self):
        self.pages = []
        self.closed = False
        self.cookies_cleared = False
        self.route_calls = []

    async def route(self, pattern, handler):
        self.route_calls.append((pattern, handler))

    async def clear_cookies(self):
        self.cookies_cleared = True

    async def close(self):
        self.closed = True


async def test_waiting_for_context_wakes_after_release(monkeypatch):
    monkeypatch.delenv("BROWSER_DISABLE_RESOURCE_BLOCKING", raising=False)
    manager = OptimizedPlaywrightManager(max_contexts=2, max_concurrent=1)
    first, second = _FakeContext(), _FakeContext()
    manager._context_in_use.extend([first, second])

    waiting = asyncio.create_task(manager.get_context())
    await asyncio.sleep(0.02)
    assert not waiting.done()

    await manager.release_context(first)
    acquired = await asyncio.wait_for(waiting, timeout=0.5)

    assert acquired is first
    assert first.cookies_cleared
    assert first in manager._context_in_use
    assert manager.get_performance_metrics()["contexts_in_use"] == 2


async def test_failed_context_cleanup_closes_and_removes_context():
    manager = OptimizedPlaywrightManager(max_contexts=2, max_concurrent=1)

    class _BrokenContext(_FakeContext):
        async def clear_cookies(self):
            raise RuntimeError("cookie cleanup failed")

    context = _BrokenContext()
    manager._context_in_use.append(context)

    with pytest.raises(RuntimeError, match="cookie cleanup failed"):
        await manager.release_context(context)

    assert context.closed
    assert context not in manager._context_in_use
    assert context not in manager._context_pool


async def test_browser_global_semaphore_caps_concurrent_work():
    manager = OptimizedPlaywrightManager(max_contexts=4, max_concurrent=2)
    active = 0
    peak = 0

    async def work():
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.02)
        active -= 1

    await asyncio.gather(
        *(manager.execute_with_semaphore(work()) for _ in range(6))
    )

    assert peak == 2
    assert manager.get_performance_metrics()["max_concurrent_reached"] == 2


def test_browser_manager_rejects_zero_capacity():
    with pytest.raises(ValueError):
        OptimizedPlaywrightManager(max_contexts=0)
    with pytest.raises(ValueError):
        OptimizedPlaywrightManager(max_concurrent=0)
