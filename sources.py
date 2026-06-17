"""
List of Google News RSS source queries.
Add/remove queries here to tune what the collector pulls in (Phase 3 tuning).

Google News RSS query format:
https://news.google.com/rss/search?q=QUERY&hl=en-US&gl=US&ceid=US:en
"""
from urllib.parse import quote

GOOGLE_NEWS_RSS_BASE = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

# Country priority order — Malaysia is #1 (main Batik Air hub), descending from there.
# filter.py uses this same order to weight relevance scoring.
COUNTRY_PRIORITY = [
    "Malaysia",
    "Indonesia",
    "Vietnam",
    "Langkawi",
    "Sri Lanka",
    "China",
    "Japan",
    "South Korea",
    "Thailand",
    "Australia",
]

# Per-country query templates — kept short (2 per country) so the total query
# count stays manageable. Malaysia gets extra dedicated queries below since
# it's the top-priority destination.
_COUNTRY_TEMPLATES = [
    "{country} tourism news",
    "{country} visa rules Uzbekistan",
]

# Raw search queries (human-readable). These get URL-encoded automatically.
QUERIES = []

for _country in COUNTRY_PRIORITY:
    for _tpl in _COUNTRY_TEMPLATES:
        QUERIES.append(_tpl.format(country=_country))

QUERIES += [
    # Malaysia-specific (priority #1 — extra depth)
    "Batik Air",
    "site:batikair.com",
    "Kuala Lumpur airport KLIA rules",
    'Langkawi OR Penang OR "Kuala Lumpur" travel',

    # Cross-cutting categories not tied to one country
    "Uzbekistan travel visa changes",
    "Uzbekistan students scholarship abroad opportunities",
    "tour agency opportunities international travel industry",
    "hotel industry news Asia",
    "tourist arrivals ranking 2026",
    "travel Instagram TikTok trends",
    "aviation industry news new routes airlines",
    "upcoming concerts Asia 2026 tourism",
    "business exhibition Guangzhou China B2B",
    "new tourist entry rules visa-free announcement",

    # Trusted Uzbek news sources (scoped via Google News site: search)
    "site:kun.uz travel OR tourism OR visa",
    "site:daryo.uz travel OR tourism OR visa",
    "site:uznews.uz travel OR tourism OR visa",
    "Uztourism Association Uzbekistan",  # Telegram channel — no indexable site, best-effort by name

    # Trusted foreign sources
    "site:tourism.gov.my",  # Tourism Malaysia
    "Malaysia Embassy Uzbekistan",  # exact embassy domain not confirmed yet
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
