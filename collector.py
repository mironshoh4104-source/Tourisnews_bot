"""Fetch and parse RSS sources into candidate news items."""
import logging
import urllib.request

import feedparser

from sources import get_sources

logger = logging.getLogger(__name__)

# Google News (and some other RSS hosts) return empty/blocked responses to
# requests without a browser-like User-Agent. feedparser's default urllib
# call doesn't set one, so fetch the raw bytes ourselves first.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _fetch_feed(url: str, timeout: int = 15):
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return feedparser.parse(raw)


def _clean_summary(raw_summary: str) -> str:
    """Google News RSS summaries often contain HTML/anchor junk; strip tags crudely."""
    import re
    text = re.sub(r"<[^>]+>", " ", raw_summary or "")
    return re.sub(r"\s+", " ", text).strip()


def collect_candidates(max_per_source: int = 8) -> list[dict]:
    """
    Pull entries from every configured RSS source.
    Returns a list of dicts: {title, summary, link, source, query, published}
    """
    candidates = []
    for src in get_sources():
        url = src["url"]
        query = src["query"]
        try:
            feed = _fetch_feed(url)
        except Exception as e:
            logger.warning("Failed to fetch feed for query '%s': %s", query, e)
            continue

        if getattr(feed, "bozo", False) and not feed.entries:
            logger.warning("Feed parse issue for query '%s': %s", query, getattr(feed, "bozo_exception", ""))
            continue

        logger.info("Query '%s': %d entries fetched", query, len(feed.entries))

        for entry in feed.entries[:max_per_source]:
            title = getattr(entry, "title", "").strip()
            link = getattr(entry, "link", "").strip()
            summary = _clean_summary(getattr(entry, "summary", ""))
            source_title = ""
            if hasattr(entry, "source") and hasattr(entry.source, "title"):
                source_title = entry.source.title
            published = getattr(entry, "published", "")

            if not title or not link:
                continue

            candidates.append({
                "title": title,
                "summary": summary,
                "link": link,
                "source": source_title or "Google News",
                "query": query,
                "published": published,
            })

    return candidates


def dedupe_by_link(candidates: list[dict]) -> list[dict]:
    """Drop duplicate candidates that share the same link within this run."""
    seen = set()
    out = []
    for c in candidates:
        if c["link"] in seen:
            continue
        seen.add(c["link"])
        out.append(c)
    return out
