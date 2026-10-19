"""Fetching layer: robots-aware HTTP, sitemap discovery, same-origin crawl, disk cache."""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.robotparser
from html import unescape
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse, urldefrag

import httpx

UA = "readlens/0.1 (+readability auditor; respects robots.txt)"

# Application surfaces are not content. Auditing /api/checkout for typography is noise,
# and its query-string variants triple-count in the site score.
SKIP_PATH = re.compile(r"^/(api|_next|cdn-cgi|wp-json|graphql)(/|$)", re.I)

SKIP_EXT = {
    ".pdf", ".zip", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".svg",
    ".ico", ".css", ".js", ".mjs", ".json", ".xml", ".txt", ".woff", ".woff2",
    ".ttf", ".otf", ".mp4", ".webm", ".mp3", ".wav", ".gz", ".tar", ".rss",
}


def normalize(url: str) -> str:
    url, _ = urldefrag(url)
    p = urlparse(url)
    scheme = p.scheme.lower() or "https"
    netloc = p.netloc.lower()
    if (scheme == "https" and netloc.endswith(":443")) or (scheme == "http" and netloc.endswith(":80")):
        netloc = netloc.rsplit(":", 1)[0]
    path = re.sub(r"/{2,}", "/", p.path) or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return urlunparse((scheme, netloc, path, "", p.query, ""))


def same_site(a: str, b: str) -> bool:
    ha, hb = urlparse(a).netloc.lower(), urlparse(b).netloc.lower()
    return ha == hb or ha.removeprefix("www.") == hb.removeprefix("www.")


def looks_like_page(url: str) -> bool:
    path = urlparse(url).path.lower()
    if SKIP_PATH.match(path):
        return False
    ext = Path(path).suffix
    return ext == "" or ext in {".html", ".htm", ".php", ".asp", ".aspx"} and ext not in SKIP_EXT


@dataclass
class Page:
    url: str
    final_url: str
    status: int
    html: str
    headers: dict = field(default_factory=dict)
    elapsed_ms: float = 0.0
    error: str | None = None
    fetched_at: float = 0.0
    from_cache: bool = False
    revalidated: bool = False

    @property
    def ok(self) -> bool:
        return self.error is None and self.status == 200 and bool(self.html)


class Cache:
    def __init__(self, root: Path | None, ttl: int = 86400):
        self.root = Path(root) if root else None
        self.ttl = ttl
        if self.root:
            self.root.mkdir(parents=True, exist_ok=True)

    def _p(self, key: str) -> Path:
        return self.root / (hashlib.sha256(key.encode()).hexdigest()[:32] + ".json")

    def get(self, key: str):
        if not self.root:
            return None
        p = self._p(key)
        if not p.exists() or (time.time() - p.stat().st_mtime) > self.ttl:
            return None
        try:
            return json.loads(p.read_text())
        except Exception:
            return None

    def put(self, key: str, value: dict) -> None:
        if not self.root:
            return
        try:
            self._p(key).write_text(json.dumps(value))
        except Exception:
            pass


class Fetcher:
    def __init__(self, *, timeout: float = 25.0, delay: float = 0.4, cache: Cache | None = None,
                 respect_robots: bool = True, user_agent: str = UA):
        self.client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Language": "en,fr;q=0.9,*;q=0.5"},
            follow_redirects=True, timeout=timeout,
        )
        self.delay = delay
        self.cache = cache or Cache(None)
        self.respect_robots = respect_robots
        self.ua = user_agent
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._last = 0.0

    def close(self) -> None:
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    # --- robots ---------------------------------------------------------
    def robots(self, url: str):
        origin = "{0.scheme}://{0.netloc}".format(urlparse(url))
        if origin not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.client.get(origin + "/robots.txt")
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            except Exception:
                rp.parse([])
            self._robots[origin] = rp
        return self._robots[origin]

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        try:
            return self.robots(url).can_fetch(self.ua, url)
        except Exception:
            return True

    # --- fetching -------------------------------------------------------
    def _throttle(self) -> None:
        gap = time.time() - self._last
        if gap < self.delay:
            time.sleep(self.delay - gap)
        self._last = time.time()

    def get(self, url: str) -> Page:
        url = normalize(url)
        hit = self.cache.get("GET " + url)
        if hit:
            page = Page(**hit)
            # Serving cached text while the browser measures the live page produces a
            # report where the comfort numbers moved and the language numbers did not,
            # with nothing saying so. Revalidate when the host gave us the means.
            validators = {}
            headers = page.headers or {}
            etag = headers.get("etag") or headers.get("ETag")
            lastmod = headers.get("last-modified") or headers.get("Last-Modified")
            if etag:
                validators["If-None-Match"] = etag
            if lastmod:
                validators["If-Modified-Since"] = lastmod
            if not validators:
                page.from_cache = True
                return page
            try:
                self._throttle()
                r = self.client.get(url, headers=validators)
                if r.status_code == 304:
                    # The server confirmed the bytes are still current, so this content
                    # is as fresh as a full fetch would have been.
                    page.from_cache = True
                    page.revalidated = True
                    page.fetched_at = time.time()
                    return page
                if r.status_code == 200 and "html" in r.headers.get("content-type", ""):
                    fresh = Page(url, str(r.url), 200, r.text, dict(r.headers),
                                 0.0, fetched_at=time.time())
                    self.cache.put("GET " + url, fresh.__dict__)
                    return fresh
            except Exception:
                pass
            page.from_cache = True
            return page
        if not self.allowed(url):
            return Page(url, url, 0, "", error="blocked by robots.txt")
        self._throttle()
        t0 = time.perf_counter()
        try:
            r = self.client.get(url)
            ctype = r.headers.get("content-type", "")
            if "html" not in ctype and "xml" not in ctype:
                page = Page(url, str(r.url), r.status_code, "", dict(r.headers),
                            (time.perf_counter() - t0) * 1000, error=f"not html ({ctype})")
            elif not (r.text or "").strip():
                page = Page(url, str(r.url), r.status_code, "", dict(r.headers),
                            (time.perf_counter() - t0) * 1000,
                            error=f"empty response body (HTTP {r.status_code})")
            else:
                page = Page(url, str(r.url), r.status_code, r.text, dict(r.headers),
                            (time.perf_counter() - t0) * 1000, fetched_at=time.time())
        except Exception as e:
            page = Page(url, url, 0, "", error=f"{type(e).__name__}: {e}")
        self.cache.put("GET " + url, page.__dict__)
        return page

    # --- discovery ------------------------------------------------------
    def sitemap_urls(self, base: str, limit: int = 500) -> list[str]:
        origin = "{0.scheme}://{0.netloc}".format(urlparse(base))
        candidates: list[str] = []
        rp = self.robots(base)
        for sm in (getattr(rp, "site_maps", lambda: None)() or []):
            candidates.append(sm)
        candidates += [origin + p for p in ("/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml")]
        seen, out = set(), []
        queue = list(dict.fromkeys(candidates))
        while queue and len(out) < limit:
            sm = queue.pop(0)
            if sm in seen:
                continue
            seen.add(sm)
            page = self.get(sm)
            if not page.ok:
                continue
            locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", page.html, re.S | re.I)
            is_index = "<sitemapindex" in page.html.lower()
            for loc in locs:
                loc = loc.strip()
                if is_index or loc.lower().endswith((".xml", ".xml.gz")):
                    queue.append(loc)
                elif same_site(base, loc) and looks_like_page(loc):
                    out.append(normalize(loc))
        return list(dict.fromkeys(out))[:limit]

    def crawl(self, base: str, max_pages: int = 20, max_depth: int = 2,
              include: str | None = None, exclude: str | None = None) -> list[str]:
        inc = re.compile(include) if include else None
        exc = re.compile(exclude) if exclude else None
        start = normalize(base)
        seen = {start}
        order = [start]
        queue = [(start, 0)]
        while queue and len(order) < max_pages * 4:
            url, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            page = self.get(url)
            if not page.ok:
                continue
            for href in re.findall(r'href=["\']([^"\'>]+)["\']', page.html):
                href = unescape(href)        # an href in markup is entity-encoded
                nxt = normalize(urljoin(page.final_url, href))
                if nxt in seen or not same_site(start, nxt) or not looks_like_page(nxt):
                    continue
                if Path(urlparse(nxt).path).suffix.lower() in SKIP_EXT:
                    continue
                if exc and exc.search(nxt):
                    continue
                if inc and not inc.search(nxt):
                    continue
                seen.add(nxt)
                order.append(nxt)
                queue.append((nxt, depth + 1))
        return order[:max_pages]

    def discover(self, base: str, max_pages: int = 20, max_depth: int = 2,
                 include: str | None = None, exclude: str | None = None,
                 use_sitemap: bool = True) -> list[str]:
        urls: list[str] = []
        if use_sitemap:
            urls = self.sitemap_urls(base)
            inc = re.compile(include) if include else None
            exc = re.compile(exclude) if exclude else None
            if inc:
                urls = [u for u in urls if inc.search(u)]
            if exc:
                urls = [u for u in urls if not exc.search(u)]
        if len(urls) < max_pages:
            crawled = self.crawl(base, max_pages=max_pages * 2, max_depth=max_depth,
                                 include=include, exclude=exclude)
            urls += [u for u in crawled if u not in urls]
        start = normalize(base)
        if start in urls:
            urls.remove(start)
        urls.insert(0, start)
        return urls[:max_pages]
