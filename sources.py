"""Free trend sources: Google News, Muslim media and Reddit RSS feeds (no API keys needed)."""

import asyncio
import calendar
import logging
import re
import time
from dataclasses import dataclass
from urllib.parse import quote_plus

import feedparser
import httpx

log = logging.getLogger(__name__)

USER_AGENT = "GuidanceCastTrendBot/1.0 (podcast research)"
MAX_AGE_DAYS = 10

NEWS_QUERY = "(muslim OR muslims OR islam OR mosque OR islamophobia) when:7d"
NEWS_REGIONS = {  # label: (hl, gl, ceid)
    "UK": ("en-GB", "GB", "GB:en"),
    "USA": ("en-US", "US", "US:en"),
    "Canada": ("en-CA", "CA", "CA:en"),
    "Australia": ("en-AU", "AU", "AU:en"),
}

MEDIA_FEEDS = {
    "5Pillars": "https://5pillarsuk.com/feed/",
    "MuslimMatters": "https://muslimmatters.org/feed/",
    "Hyphen": "https://hyphenonline.com/feed/",
    "The Muslim Vibe": "https://themuslimvibe.com/feed",
    "CAIR": "https://www.cair.com/feed/",
}

SUBREDDITS = ["islam", "MuslimLounge", "converts", "MuslimMarriage", "progressive_islam", "ukmuslims"]


@dataclass
class Item:
    source: str
    title: str
    link: str
    summary: str = ""


def _clean(html: str, limit: int = 220) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _is_recent(entry) -> bool:
    published = entry.get("published_parsed") or entry.get("updated_parsed")
    if not published:
        return True
    return time.time() - calendar.timegm(published) < MAX_AGE_DAYS * 86400


async def _fetch(client: httpx.AsyncClient, source: str, url: str, limit: int) -> list[Item]:
    try:
        resp = await client.get(url)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        log.warning("Skipping %s: %s", source, e)
        return []
    feed = feedparser.parse(resp.content)
    return [
        Item(source, e.get("title", "").strip(), e.get("link", ""), _clean(e.get("summary", "")))
        for e in feed.entries
        if _is_recent(e)
    ][:limit]


async def _reddit(client: httpx.AsyncClient) -> list[Item]:
    # Reddit rate-limits bursts, so fetch subreddits one at a time with a pause.
    items = []
    for sub in SUBREDDITS:
        url = f"https://www.reddit.com/r/{sub}/top/.rss?t=week"
        batch = await _fetch(client, f"r/{sub}", url, 8)
        if not batch:  # usually a 429 - wait and retry once
            await asyncio.sleep(15)
            batch = await _fetch(client, f"r/{sub}", url, 8)
        items += batch
        await asyncio.sleep(5)
    return items


async def gather() -> list[Item]:
    """Collect recent headlines and discussions from every source."""
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=20
    ) as client:
        tasks = [
            _fetch(
                client,
                f"Google News {label}",
                f"https://news.google.com/rss/search?q={quote_plus(NEWS_QUERY)}&hl={hl}&gl={gl}&ceid={ceid}",
                20,
            )
            for label, (hl, gl, ceid) in NEWS_REGIONS.items()
        ]
        tasks += [_fetch(client, name, url, 10) for name, url in MEDIA_FEEDS.items()]
        tasks.append(_reddit(client))
        results = await asyncio.gather(*tasks)

    seen, items = set(), []
    for item in (i for batch in results for i in batch):
        key = item.title.lower()[:80]
        if item.title and key not in seen:
            seen.add(key)
            items.append(item)
    log.info("Gathered %d items", len(items))
    return items


def format_items(items: list[Item]) -> str:
    lines = []
    for i in items:
        line = f"[{i.source}] {i.title} | {i.link}"
        if i.summary and not i.source.startswith("Google News"):
            line += f"\n    {i.summary}"
        lines.append(line)
    return "\n".join(lines)
