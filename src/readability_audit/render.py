"""Headless-browser probe: computed typography, contrast, layout comfort.

One browser, N concurrent tabs. The async API is used on purpose: Playwright's sync
objects are bound to the thread that made them, so thread-parallelism would mean N
Chromium processes instead of N tabs — several hundred megabytes each.
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from pathlib import Path

PROBE = (Path(__file__).parent / "probe.js").read_text()

INIT = """
window.__readability = {cls: 0, lcp: 0, shifts: 0};
try {
  new PerformanceObserver((l) => { for (const e of l.getEntries()) {
    if (!e.hadRecentInput) { window.__readability.cls += e.value; window.__readability.shifts++; } } })
    .observe({type: 'layout-shift', buffered: true});
  new PerformanceObserver((l) => { const es = l.getEntries();
    window.__readability.lcp = es[es.length - 1].startTime; })
    .observe({type: 'largest-contentful-paint', buffered: true});
} catch (e) {}
"""

DEFAULT_VIEWPORTS = {"desktop": (1440, 900), "mobile": (390, 844)}

# Memory is base + marginal, not per-tab: the browser process and its shared mappings are
# paid once. Measured by PSS on this repo's own audits (8 pages of tokenade.net):
#   concurrency 1 -> 309 MB / 31.3s · 4 -> 579 MB / 14.5s · 8 -> 723 MB / 11.4s
# so ~300 MB of base and ~90 MB per extra concurrent page. The constants below keep a
# margin over that, because a heavy page (large images, many web fonts) costs more.
BASE_MB = 350
MB_PER_EXTRA_TAB = 130
# Never eat into the last of the machine's memory, whatever concurrency was asked for.
RAM_FLOOR_MB = 800
MAX_CONCURRENCY = 8

LAUNCH_ARGS = [
    "--disable-dev-shm-usage",        # /dev/shm is small in containers; use /tmp
    "--font-render-hinting=none",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-features=Translate,BackForwardCache,AcceptCHFrame",
    "--no-first-run",
]


def available_mb() -> int | None:
    """MemAvailable in MB, or None where the kernel does not publish it."""
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except Exception:
        pass
    try:                                   # portable fallback, ignores cache reclaim
        return (os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")) // (1024 * 1024)
    except Exception:
        return None


def estimated_mb(concurrency: int, base_mb: int = BASE_MB,
                 extra_mb: int = MB_PER_EXTRA_TAB) -> int:
    return base_mb + extra_mb * max(0, concurrency - 1)


def safe_concurrency(requested: int, *, base_mb: int = BASE_MB,
                     extra_mb: int = MB_PER_EXTRA_TAB,
                     floor_mb: int = RAM_FLOOR_MB) -> tuple[int, str]:
    """Clamp the requested concurrency to what this machine can actually hold."""
    requested = max(1, min(requested, MAX_CONCURRENCY))
    avail = available_mb()
    if avail is None:
        return requested, "memory unknown, using the requested concurrency"
    budget = avail - floor_mb
    if budget < base_mb:
        return 1, (f"only {avail} MB available: running one page at a time, and even that "
                   f"needs about {base_mb} MB")
    allowed = max(1, min(requested, 1 + int((budget - base_mb) // extra_mb)))
    if allowed < requested:
        return allowed, (f"reduced {requested} to {allowed}: {avail} MB available, keeping "
                         f"{floor_mb} MB free (~{estimated_mb(allowed)} MB for the browser)")
    return allowed, f"{avail} MB free, ~{estimated_mb(allowed)} MB for the browser"


@dataclass
class RenderResult:
    url: str
    viewports: dict = field(default_factory=dict)
    screenshots: dict = field(default_factory=dict)
    dark_mode: dict | None = None
    html: str | None = None          # the DOM as it stands after scripts have run
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.viewports)


class Renderer:
    """Reusable browser. `render(url)` for one page, `render_many(urls)` for a batch."""

    def __init__(self, viewports: dict | None = None, *, timeout: int = 45000,
                 check_dark: bool = True, user_agent: str | None = None,
                 screenshot_dir: Path | None = None, full_page_shot: bool = False,
                 concurrency: int = 4, base_mb: int = BASE_MB,
                 extra_mb: int = MB_PER_EXTRA_TAB, ram_floor_mb: int = RAM_FLOOR_MB):
        self.viewports = viewports or DEFAULT_VIEWPORTS
        self.timeout = timeout
        self.check_dark = check_dark
        self.user_agent = user_agent
        self.screenshot_dir = Path(screenshot_dir) if screenshot_dir else None
        self.full_page_shot = full_page_shot
        self.requested_concurrency = concurrency
        self.base_mb = base_mb
        self.extra_mb = extra_mb
        self.ram_floor_mb = ram_floor_mb
        self.concurrency, self.concurrency_note = safe_concurrency(
            concurrency, base_mb=base_mb, extra_mb=extra_mb, floor_mb=ram_floor_mb)
        self.error: str | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pw = None
        self._browser = None

    # --- lifecycle ------------------------------------------------------
    def __enter__(self):
        try:
            self._loop = asyncio.new_event_loop()
            self._loop.run_until_complete(self._start())
        except Exception as e:
            self.error = f"playwright unavailable: {type(e).__name__}: {e}"
        return self

    def __exit__(self, *a):
        if self._loop is None:
            return
        try:
            self._loop.run_until_complete(self._stop())
        except Exception:
            pass
        finally:
            try:
                self._loop.close()
            except Exception:
                pass
            self._loop = None

    async def _start(self):
        from playwright.async_api import async_playwright
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(args=LAUNCH_ARGS)

    async def _stop(self):
        for obj, meth in ((self._browser, "close"), (self._pw, "stop")):
            try:
                if obj is not None:
                    await getattr(obj, meth)()
            except Exception:
                pass
        self._browser = self._pw = None

    # --- work -----------------------------------------------------------
    async def _one_viewport(self, url: str, name: str, size: tuple[int, int],
                            res: RenderResult) -> None:
        w, h = size
        ctx = None
        try:
            ctx = await self._browser.new_context(
                viewport={"width": w, "height": h},
                device_scale_factor=2 if name == "mobile" else 1,
                is_mobile=(name == "mobile"), has_touch=(name == "mobile"),
                user_agent=self.user_agent, locale="en-US",
            )
            await ctx.add_init_script(INIT)
            page = await ctx.new_page()
            await page.goto(url, wait_until="load", timeout=self.timeout)
            try:
                await page.wait_for_load_state("networkidle", timeout=6000)
            except Exception:
                pass
            await page.wait_for_timeout(600)
            res.viewports[name] = await page.evaluate(PROBE)
            if name == "desktop" or res.html is None:
                # The served HTML and the rendered DOM are different documents on any
                # client-rendered page. Everything downstream must read the same one.
                try:
                    res.html = await page.content()
                except Exception:
                    pass
            if self.screenshot_dir:
                self.screenshot_dir.mkdir(parents=True, exist_ok=True)
                safe = "".join(c if c.isalnum() else "_" for c in url)[-60:]
                sp = self.screenshot_dir / f"{safe}_{name}.png"
                await page.screenshot(path=str(sp), full_page=self.full_page_shot)
                res.screenshots[name] = str(sp)
            if self.check_dark and name == "desktop":
                await page.emulate_media(color_scheme="dark")
                await page.wait_for_timeout(300)
                res.dark_mode = await page.evaluate(
                    "() => ({bg: getComputedStyle(document.body).backgroundColor,"
                    " color: getComputedStyle(document.body).color,"
                    " scheme: getComputedStyle(document.documentElement).colorScheme})")
        except Exception as e:
            res.error = f"{type(e).__name__}: {e}"
        finally:
            if ctx is not None:
                try:
                    await ctx.close()          # closes the tab; frees the renderer process
                except Exception:
                    pass

    async def _one_url(self, url: str) -> RenderResult:
        res = RenderResult(url)
        # Viewports of one page run one after the other: two tabs of the same page at
        # once doubles the peak for no wall-clock gain worth the memory.
        for name, size in self.viewports.items():
            await self._one_viewport(url, name, size, res)
        return res

    async def _many(self, urls: list[str], on_done=None) -> dict[str, RenderResult]:
        sem = asyncio.Semaphore(self.concurrency)
        out: dict[str, RenderResult] = {}
        done = 0

        async def run(u: str):
            nonlocal done
            async with sem:
                # If memory got tight while the batch was running, wait rather than swap.
                for _ in range(20):
                    avail = available_mb()
                    if avail is None or avail > self.ram_floor_mb:
                        break
                    await asyncio.sleep(1.0)
                out[u] = await self._one_url(u)
            done += 1
            if on_done:
                on_done(done, len(urls), u)

        await asyncio.gather(*(run(u) for u in urls))
        return out

    def render(self, url: str) -> RenderResult:
        if self._browser is None or self._loop is None:
            return RenderResult(url, error=self.error or "browser not started")
        return self._loop.run_until_complete(self._one_url(url))

    def render_many(self, urls: list[str], on_done=None) -> dict[str, RenderResult]:
        if self._browser is None or self._loop is None:
            return {u: RenderResult(u, error=self.error or "browser not started") for u in urls}
        return self._loop.run_until_complete(self._many(list(urls), on_done))


def render(url: str, viewports: dict | None = None, *, screenshot_dir: Path | None = None,
           timeout: int = 45000, check_dark: bool = True, user_agent: str | None = None,
           full_page_shot: bool = False) -> RenderResult:
    """One-shot convenience wrapper. Use Renderer for more than one page."""
    with Renderer(viewports, timeout=timeout, check_dark=check_dark, user_agent=user_agent,
                  screenshot_dir=screenshot_dir, full_page_shot=full_page_shot) as r:
        if r.error:
            return RenderResult(url, error=r.error)
        return r.render(url)
