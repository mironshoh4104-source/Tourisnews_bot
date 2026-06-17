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
        _client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


SYSTEM_PROMPT = """You are a relevance filter for a Telegram travel-news channel aimed at \
Uzbek travelers and Batik Air destinations (Malaysia, Kuala Lumpur, Langkawi, Penang, etc.).

Relevant = useful to Uzbek travelers, OR tied to a Batik Air destination, OR a visa/airport/\
flight rule change affecting Uzbek/CIS citizens.

Reject: duplicates of older news, ads/spam, unrelated regions, opinion fluff with no news value.

Respond with JSON ONLY, no markdown fences, no extra text, in this exact shape:
{"relevant": true|false, "score": 0-100, "reason": "short reason", "category": "visa|airport|route|destination|other"}
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
        logger.warning("Relevance scoring failed for '%s': %s", candidate.get("title", ""), e)
        return {"relevant": False, "score": 0, "reason": f"scoring_error: {e}", "category": "other"}


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
