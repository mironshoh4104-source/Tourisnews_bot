"""
Telegram handlers + buttons + scheduler entry for the @batikairuz travel news bot.

Phase 1: manual trigger via /run.
Phase 2: APScheduler daily job at config.RUN_TIME (wired below, started in main()).
"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import config
import db
from collector import collect_candidates, dedupe_by_link
from filter import filter_and_rank
from writer import write_post

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# In-memory queue of not-yet-drafted candidates for the current cycle, keyed by
# nothing in particular since this is a single-admin bot. Holds dicts with the
# same shape as collector candidates plus score/reason/category.
QUEUE_KEY = "candidate_queue"
AWAITING_EDIT_KEY = "awaiting_edit_draft_id"


def _build_keyboard(draft_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve & Post", callback_data=f"approve:{draft_id}"),
            InlineKeyboardButton("✏️ Edit", callback_data=f"edit:{draft_id}"),
            InlineKeyboardButton("⏭ Skip", callback_data=f"skip:{draft_id}"),
        ]
    ])


async def _draft_and_send_next(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Pop the next candidate off the queue, write its post, save as pending,
    and send it to the admin with action buttons. If the queue is empty, say so."""
    queue = context.bot_data.get(QUEUE_KEY, [])
    if not queue:
        await context.bot.send_message(chat_id=chat_id, text="No more candidates in this cycle.")
        return

    candidate = queue.pop(0)
    context.bot_data[QUEUE_KEY] = queue

    item_hash = db.compute_item_hash(candidate["link"], candidate["title"])
    if db.is_posted(item_hash):
        # Already posted in a previous cycle — skip silently and try the next one.
        await _draft_and_send_next(context, chat_id)
        return

    try:
        draft_text = write_post(candidate)
    except Exception as e:
        logger.exception("Writer failed for '%s'", candidate["title"])
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ Failed to draft post for '{candidate['title']}': {e}\nTrying next candidate...",
        )
        await _draft_and_send_next(context, chat_id)
        return

    draft_id = db.save_pending_draft(
        item_hash=item_hash,
        draft_text=draft_text,
        url=candidate["link"],
        title=candidate["title"],
        source=candidate["source"],
    )

    header = f"📰 Score {candidate.get('score', '?')} · {candidate.get('category', '?')}\n\n"
    message = await context.bot.send_message(
        chat_id=chat_id,
        text=header + draft_text,
        reply_markup=_build_keyboard(draft_id),
    )
    db.set_pending_message_id(draft_id, message.message_id)


async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manual trigger: collector -> filter -> queue -> draft first item."""
    chat_id = update.effective_chat.id
    await update.message.reply_text("Collecting candidate news...")

    candidates = collect_candidates()
    candidates = dedupe_by_link(candidates)

    # Drop anything already posted before spending Claude calls scoring it.
    fresh = []
    for c in candidates:
        h = db.compute_item_hash(c["link"], c["title"])
        if not db.is_posted(h):
            fresh.append(c)

    if not fresh:
        await update.message.reply_text("No fresh candidates found.")
        return

    await update.message.reply_text(f"Scoring {len(fresh)} candidates with Claude...")
    ranked = filter_and_rank(fresh)

    if not ranked:
        await update.message.reply_text("No candidates scored >= relevance threshold.")
        return

    context.bot_data[QUEUE_KEY] = ranked
    await update.message.reply_text(f"Kept {len(ranked)} relevant item(s). Drafting top pick...")
    await _draft_and_send_next(context, chat_id)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """First-contact greeting. Telegram requires the user to message the bot
    before it can DM them, so this also doubles as the 'are you alive' check."""
    await update.message.reply_text(
        "👋 BatikAirUZ travel news bot is running.\n\n"
        "/run — collect, score, and draft today's top travel-news item\n"
        "/myid — show this chat's numeric ID (for ADMIN_CHAT_ID setup)"
    )


async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Temporary helper to discover ADMIN_CHAT_ID. Remove after setup."""
    await update.message.reply_text(f"Your chat id: {update.effective_chat.id}")


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action, _, draft_id = query.data.partition(":")
    draft = db.get_pending_draft(draft_id)
    if not draft:
        await query.edit_message_text("This draft no longer exists (already handled or expired).")
        return

    chat_id = query.message.chat_id

    if action == "approve":
        try:
            await context.bot.send_message(chat_id=config.CHANNEL_ID, text=draft["draft_text"])
        except Exception as e:
            logger.exception("Failed to publish draft %s", draft_id)
            await query.edit_message_text(f"❌ Failed to publish: {e}")
            return

        db.mark_posted(draft["item_hash"], draft["url"], draft["title"])
        db.delete_pending(draft_id)
        await query.edit_message_text(
            query.message.text + "\n\n✅ Published to " + config.CHANNEL_ID
        )

    elif action == "edit":
        context.bot_data[AWAITING_EDIT_KEY] = draft_id
        await query.edit_message_text(
            query.message.text + "\n\n✏️ Reply to this chat with the corrected post text."
        )

    elif action == "skip":
        db.delete_pending(draft_id)
        await query.edit_message_text(query.message.text + "\n\n⏭ Skipped.")
        await _draft_and_send_next(context, chat_id)

    else:
        await query.edit_message_text("Unknown action.")


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin replies used to correct a draft after pressing Edit."""
    draft_id = context.bot_data.get(AWAITING_EDIT_KEY)
    if not draft_id:
        return  # Not in an edit flow; ignore stray text.

    draft = db.get_pending_draft(draft_id)
    if not draft:
        context.bot_data[AWAITING_EDIT_KEY] = None
        await update.message.reply_text("That draft no longer exists.")
        return

    new_text = update.message.text
    db.update_pending_text(draft_id, new_text)
    context.bot_data[AWAITING_EDIT_KEY] = None

    chat_id = update.effective_chat.id
    message = await context.bot.send_message(
        chat_id=chat_id,
        text="📝 Updated draft:\n\n" + new_text,
        reply_markup=_build_keyboard(draft_id),
    )
    db.set_pending_message_id(draft_id, message.message_id)


async def run_daily_cycle(application: Application):
    """APScheduler job target: runs the same flow as /run, without needing a
    message to reply to."""
    chat_id = int(config.ADMIN_CHAT_ID)
    bot_data = application.bot_data

    candidates = collect_candidates()
    candidates = dedupe_by_link(candidates)
    fresh = [c for c in candidates if not db.is_posted(db.compute_item_hash(c["link"], c["title"]))]

    if not fresh:
        await application.bot.send_message(chat_id=chat_id, text="Daily run: no fresh candidates found.")
        return

    ranked = filter_and_rank(fresh)
    if not ranked:
        await application.bot.send_message(chat_id=chat_id, text="Daily run: nothing scored above threshold.")
        return

    bot_data[QUEUE_KEY] = ranked

    class _Ctx:
        """Minimal shim so _draft_and_send_next can reuse application.bot_data/bot."""
        def __init__(self, app):
            self.bot_data = app.bot_data
            self.bot = app.bot

    await _draft_and_send_next(_Ctx(application), chat_id)


def main():
    config.validate()
    db.init_db()

    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("run", cmd_run))
    application.add_handler(CommandHandler("myid", cmd_myid))
    application.add_handler(CallbackQueryHandler(on_button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    scheduler = AsyncIOScheduler(timezone=config.TIMEZONE)
    hour, minute = (int(p) for p in config.RUN_TIME.split(":"))
    scheduler.add_job(
        run_daily_cycle,
        "cron",
        hour=hour,
        minute=minute,
        args=[application],
    )
    application.job_queue  # ensures job queue is initialized before scheduler starts alongside it
    scheduler.start()

    logger.info("Bot starting. Daily cycle scheduled at %s %s.", config.RUN_TIME, config.TIMEZONE)
    application.run_polling()


if __name__ == "__main__":
    main()
