"""Claude bilingual (RU+UZ) Telegram post writer."""
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


SYSTEM_PROMPT = """You write bilingual (Russian + Uzbek) Telegram posts for @batikairuz, a \
travel-news channel for Uzbek travelers and Batik Air destinations.

Goal: every post should feel genuinely useful to a Uzbek traveler — practical, specific, \
worth acting on — so they keep coming back to the channel for the next post.

Tone: informative, engaging, channel-style — not robotic. Lead with the angle that matters \
most to the reader (what changed, what they can do, what to watch out for), not a generic \
recap. If the news involves a rule, opportunity, or deadline, make clear exactly who it \
applies to and who it doesn't.
Never invent facts. Only use what's in the source provided. If a detail isn't in the source, leave it out.
Keep it tight enough for a Telegram post (no walls of text).
Always include the source line — the admin verifies against it before approving.

Output ONLY the final post text, in exactly this structure (keep the literal separators \
and emoji, fill in the bracketed parts, omit nothing):

🇲🇾 [Emoji hook headline]

[2–4 key facts, short lines]

✈️ Почему это важно: [one line — why it matters for the traveler]

──────────
🇺🇿 [Uzbek version of the same: hook + facts + "Nega muhim:" line]

📍 Источник / Manba: [source name] — [the exact Link given to you, unchanged, as a bare URL]
#BatikAir #Malaysia #Путешествия #Sayohat

The bare URL in the source line must be copied exactly from the "Link" field you're given — \
do not shorten it, wrap it in markdown, or alter it. Telegram auto-renders bare URLs as \
clickable links, so do not add brackets or markdown around it.

Do not add commentary before or after the post. Do not wrap in markdown fences.
"""


def write_post(article: dict) -> str:
    """Generate the bilingual post text for the chosen article dict
    (expects title, summary, source, link)."""
    user_content = (
        f"Title: {article['title']}\n"
        f"Summary: {article['summary']}\n"
        f"Source: {article['source']}\n"
        f"Link: {article['link']}"
    )

    resp = _get_client().messages.create(
        model=config.MODEL,
        max_tokens=800,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    text = resp.content[0].text.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
    return text
