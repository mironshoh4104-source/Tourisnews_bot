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

Respond with JSON ONLY, no markdown fences, no extra text, in this exact shape:
{"relevant": true|false, "score": 0-100, "reason": "short reason", "category": "visa|airport|route|destination|event|exhibition|education|hotel|ranking|social_trend|aviation|concert|rules|other"}
"""


def score_candidate(candidate: dict) -> dict:
    """Call Claude to score one candidate. Returns the parsed JSON dict, or a
    safe default (relevant=False, score=0) if the call or parse fails."""
    user_content = (
        f"Title: {candidate['title']}\n"
        f"Summary: {candidate['summary']}\n"
        f"Source: {candidate['source']}\n"
        f"Link: {candidate['link']}\n"
        f"Matched query: {candidate.get('query', '')}"
    )

    try:
        resp = _get_client().messages.create(
            model=config.MODEL,
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        text = resp.content[0].text.strip()
        # Guard against accidental markdown fencing
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        result = json.loads(text)
        result.setdefault("relevant", False)
        result.setdefault("score", 0)
        result.setdefault("reason", "")
        result.setdefault("category", "other")
        return result
    except Exception as e:
        cause = getattr(e, "__cause__", None)
        logger.exception(
            "Relevance scoring failed for '%s' (type=%s, cause=%s)",
            candidate.get("title", ""), type(e).__name__, cause,
        )
        return {
            "relevant": False,
            "score": 0,
            "reason": f"scoring_error: {type(e).__name__}: {cause or e}",
            "category": "other",
        }


def filter_and_rank(candidates: list[dict], debug_all: list[dict] | None = None) -> list[dict]:
    """Score every candidate, keep score >= threshold, sort desc, attach score info.

    If debug_all is passed (a list), every scored candidate (pass or fail) is
    appended to it as {title, score, relevant, reason} so callers can inspect
    why nothing made the cut.
    """
    scored = []
    for c in candidates:
        result = score_candidate(c)
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
