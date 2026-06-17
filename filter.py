"""Claude relevance scoring for candidate news items."""
import json
import logging

from anthropic import Anthropic

import config

logger = logging.getLogger(__name__)

_client = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=60.0, max_retries=3)
    return _client


SYSTEM_PROMPT = """You are a relevance filter for @batikairuz, a Telegram travel-news channel \
for Uzbek travelers, aimed at making readers want to keep following the channel.

DESTINATION PRIORITY (score higher for countries earlier in this list — Malaysia is the \
top priority since it's the main Batik Air hub; relevance is not limited to this list, but \
items about these countries should be scored higher when otherwise comparable):
1. Malaysia (incl. Kuala Lumpur, Langkawi, Penang, KLIA)
2. Indonesia
3. Vietnam
4. Langkawi
5. Sri Lanka
6. China
7. Japan
8. South Korea
9. Thailand
10. Australia

CONTENT CATEGORIES considered relevant (any one of these qualifies an item):
- Events/festivals in KL, Bali, Singapore, or other Batik Air-region cities
- B2B / business exhibitions abroad (e.g. trade fairs in Guangzhou, China)
- Opportunities other countries offer to Uzbek citizens (visa-free deals, work/study programs)
- University news — new programs, scholarships, or opportunities for Uzbek students abroad
- New parks, attractions, or entertainment venues worth visiting
- Opportunities or news relevant to tour agencies
- Hotel industry news in relevant countries
- New tourist rules — and who they apply to / don't apply to (always say who is affected)
- Tourism rankings — how a country's tourist satisfaction/popularity is trending
- Travel trends on social media (Instagram/TikTok) relevant to a destination
- Aviation industry news worldwide, especially anything Uzbekistan/CIS aviation lacks
- Major upcoming concerts/events likely to draw tourists to a destination
- Global travel news/trends worth comparing to Uzbekistan's own travel scene
- Visa/airport/flight rule changes affecting Uzbek or CIS citizens specifically

Reject: duplicates of older news, ads/spam, regions with no plausible tie to the above \
categories or destinations, opinion fluff with no concrete news value.

Respond with JSON ONLY, no markdown fences, no extra text. You will be given a NUMBERED LIST \
of candidates. Return a JSON ARRAY with exactly one object per candidate, in the same order, \
each shaped like:
{"index": 0, "relevant": true|false, "score": 0-100, "reason": "short reason", "category": "visa|airport|route|destination|event|exhibition|education|hotel|ranking|social_trend|aviation|concert|rules|other"}

Return ONLY the JSON array, nothing else — no markdown fences, no commentary.
"""


def _parse_json_array(text: str) -> list[dict]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    return json.loads(text)


def score_batch(candidates: list[dict]) -> list[dict]:
    """Score a batch (list) of candidates in a single Claude call. Returns a
    list of result dicts in the same order as the input. Falls back to
    relevant=False entries for the whole batch if the call or parse fails."""
    if not candidates:
        return []

    lines = []
    for i, c in enumerate(candidates):
        lines.append(
            f"[{i}]\n"
            f"Title: {c['title']}\n"
            f"Summary: {c['summary']}\n"
            f"Source: {c['source']}\n"
            f"Link: {c['link']}\n"
            f"Matched query: {c.get('query', '')}"
        )
    user_content = "\n\n".join(lines)

    try:
        resp = _get_client().messages.create(
            model=config.FILTER_MODEL,
            max_tokens=300 + 120 * len(candidates),
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        text = resp.content[0].text.strip()
        parsed = _parse_json_array(text)

        by_index = {}
        for item in parsed:
            idx = item.get("index")
            if isinstance(idx, int):
                by_index[idx] = item

        results = []
        for i in range(len(candidates)):
            r = by_index.get(i, {})
            results.append({
                "relevant": r.get("relevant", False),
                "score": r.get("score", 0),
                "reason": r.get("reason", ""),
                "category": r.get("category", "other"),
            })
        return results
    except Exception as e:
        cause = getattr(e, "__cause__", None)
        logger.exception(
            "Batch relevance scoring failed for %d candidates (type=%s, cause=%s)",
            len(candidates), type(e).__name__, cause,
        )
        return [{
            "relevant": False,
            "score": 0,
            "reason": f"scoring_error: {type(e).__name__}: {cause or e}",
            "category": "other",
        } for _ in candidates]


def filter_and_rank(candidates: list[dict], debug_all: list[dict] | None = None) -> list[dict]:
    """Score every candidate in batches (config.FILTER_BATCH_SIZE per Claude call),
    keep score >= threshold, sort desc, attach score info.

    If debug_all is passed (a list), every scored candidate (pass or fail) is
    appended to it as {title, score, relevant, reason} so callers can inspect
    why nothing made the cut.
    """
    scored = []
    batch_size = max(1, config.FILTER_BATCH_SIZE)

    for start in range(0, len(candidates), batch_size):
        batch = candidates[start:start + batch_size]
        results = score_batch(batch)

        for c, result in zip(batch, results):
            logger.info(
                "Scored '%s': relevant=%s score=%s reason=%s",
                c.get("title", "")[:80], result.get("relevant"), result.get("score"), result.get("reason"),
            )
            if debug_all is not None:
                debug_all.append({
                    "title": c.get("title", ""),
                    "score": result.get("score", 0),
                    "relevant": result.get("relevant", False),
                    "reason": result.get("reason", ""),
                })
            if result.get("relevant") and result.get("score", 0) >= config.RELEVANCE_THRESHOLD:
                item = dict(c)
                item["score"] = result["score"]
                item["reason"] = result.get("reason", "")
                item["category"] = result.get("category", "other")
                scored.append(item)

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:config.MAX_CANDIDATES_KEPT]
