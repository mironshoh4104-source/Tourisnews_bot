"""
List of Google News RSS source queries.
Add/remove queries here to tune what the collector pulls in (Phase 3 tuning).

Google News RSS query format:
https://news.google.com/rss/search?q=QUERY&hl=en-US&gl=US&ceid=US:en
"""
from urllib.parse import quote

GOOGLE_NEWS_RSS_BASE = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

# Raw search queries (human-readable). These get URL-encoded automatically.
QUERIES = [
    "Malaysia visa Uzbekistan",
    "Uzbekistan travel visa changes",
    "Batik Air",
    "Kuala Lumpur airport KLIA rules",
    "Thailand visa Uzbekistan",
    "Malaysia tourism news",
    'Langkawi OR Penang OR "Kuala Lumpur" travel',
]


def get_feed_urls():
    """Return the list of fully-formed, URL-encoded Google News RSS feed URLs."""
    return [GOOGLE_NEWS_RSS_BASE.format(query=quote(q)) for q in QUERIES]


# Each entry pairs a feed URL with the query that produced it, for logging/debugging.
def get_sources():
    return [
        {"query": q, "url": GOOGLE_NEWS_RSS_BASE.format(query=quote(q))}
        for q in QUERIES
    ]
