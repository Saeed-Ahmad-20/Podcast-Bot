"""GuidanceCast trend bot for Telegram."""

import logging
import os
from datetime import time
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

from telegram import BotCommand, Update  # noqa: E402
from telegram.constants import ChatAction, ParseMode  # noqa: E402
from telegram.error import BadRequest, NetworkError  # noqa: E402
from telegram.ext import Application, CommandHandler, ContextTypes, filters  # noqa: E402

import research  # noqa: E402

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("guidancecast")

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"].strip().strip("\"'")
PROXY = os.getenv("TELEGRAM_PROXY", "").strip()
ALLOWED_IDS = {int(x) for x in os.getenv("ALLOWED_USER_IDS", "").replace(" ", "").split(",") if x}
TIMEZONE = ZoneInfo(os.getenv("TIMEZONE", "Europe/London"))
DAILY_TIME = time.fromisoformat(os.getenv("DAILY_BRIEF_TIME", "08:00")).replace(tzinfo=TIMEZONE)
TELEGRAM_LIMIT = 4000

# Only people listed in ALLOWED_USER_IDS can use the bot (each request costs API credits).
# If the list is empty the bot answers anyone, so /myid can be used during setup.
AUTH = filters.User(user_id=ALLOWED_IDS) if ALLOWED_IDS else filters.ALL

HELP = (
    "<b>GuidanceCast Trend Bot</b> 🎙\n\n"
    "/trends - hottest topics in the Western Muslim world right now\n"
    "/ideas - 5 episode ideas from what's trending\n"
    "/ideas <i>topic</i> - episode ideas on a topic you choose\n"
    "/brief - full weekly briefing (trends, pitches, upcoming dates)\n"
    "/daily_on - get the briefing every morning\n"
    "/daily_off - stop the morning briefing\n"
    "/myid - show your Telegram user ID\n\n"
    "Each request takes about a minute while I read the latest news and discussions."
)


def split_message(text: str) -> list[str]:
    """Split on paragraph breaks so each chunk fits Telegram's message limit."""
    chunks, current = [], ""
    for para in text.split("\n\n"):
        while len(para) > TELEGRAM_LIMIT:
            chunks.append(para[:TELEGRAM_LIMIT])
            para = para[TELEGRAM_LIMIT:]
        if len(current) + len(para) + 2 > TELEGRAM_LIMIT:
            chunks.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        chunks.append(current)
    return chunks


async def send_long(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str) -> None:
    for chunk in split_message(text):
        try:
            await context.bot.send_message(
                chat_id, chunk, parse_mode=ParseMode.HTML, disable_web_page_preview=True
            )
        except BadRequest:
            # Malformed HTML from a chunk split - fall back to plain text.
            await context.bot.send_message(chat_id, chunk, disable_web_page_preview=True)


async def run_research(context: ContextTypes.DEFAULT_TYPE, chat_id: int, label: str, coro) -> None:
    status = await context.bot.send_message(chat_id, f"🔎 Researching {label}... (about a minute)")
    await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
    try:
        result = await coro
    except research.ResearchError as e:
        await status.edit_text(str(e))
        return
    except Exception:
        log.exception("Research failed")
        await status.edit_text("⚠️ Something went wrong. Please try again in a few minutes.")
        return

    await status.delete()
    await send_long(context, chat_id, result)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_html(HELP)


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"Your Telegram user ID is {update.effective_user.id}")


async def trends(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await run_research(context, update.effective_chat.id, "trending topics", research.hot_topics())


async def ideas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    focus = " ".join(context.args).strip() or None
    label = f"episode ideas on “{focus}”" if focus else "episode ideas"
    await run_research(context, update.effective_chat.id, label, research.podcast_ideas(focus))


async def brief(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await run_research(context, update.effective_chat.id, "this week's briefing", research.weekly_brief())


async def daily_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await run_research(context, context.job.chat_id, "your morning briefing", research.weekly_brief())


async def daily_on(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    for job in context.job_queue.get_jobs_by_name(str(chat_id)):
        job.schedule_removal()
    context.job_queue.run_daily(daily_job, DAILY_TIME, chat_id=chat_id, name=str(chat_id))
    await update.message.reply_text(
        f"✅ You'll get a briefing every day at {DAILY_TIME.strftime('%H:%M')} ({TIMEZONE.key})."
    )


async def daily_off(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    jobs = context.job_queue.get_jobs_by_name(str(update.effective_chat.id))
    for job in jobs:
        job.schedule_removal()
    await update.message.reply_text("🛑 Daily briefing stopped." if jobs else "No daily briefing was set.")


COMMANDS = [
    BotCommand("trends", "Hottest topics in the Western Muslim world"),
    BotCommand("ideas", "Podcast episode ideas (add a topic: /ideas marriage)"),
    BotCommand("brief", "Full briefing: trends, pitches, upcoming dates"),
    BotCommand("daily_on", "Get the briefing every morning"),
    BotCommand("daily_off", "Stop the morning briefing"),
    BotCommand("help", "Show all commands"),
    BotCommand("myid", "Show your Telegram user ID"),
]


async def setup(app: Application) -> None:
    await app.bot.set_my_commands(COMMANDS)  # fills the "/" menu in Telegram
    await restore_daily_jobs(app)


async def restore_daily_jobs(app: Application) -> None:
    """Re-schedule daily briefings for chats listed in DAILY_CHAT_IDS after a restart."""
    for chat_id in os.getenv("DAILY_CHAT_IDS", "").replace(" ", "").split(","):
        if chat_id:
            app.job_queue.run_daily(daily_job, DAILY_TIME, chat_id=int(chat_id), name=chat_id)
            log.info("Daily briefing scheduled for chat %s", chat_id)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    if isinstance(context.error, NetworkError):
        # Telegram unreachable for a moment - the bot retries on its own.
        log.warning("Can't reach Telegram (%s), retrying...", context.error)
    else:
        log.error("Unexpected error", exc_info=context.error)


def main() -> None:
    if not ALLOWED_IDS:
        log.warning("ALLOWED_USER_IDS is empty - the bot will answer ANYONE. Set it in .env.")

    if any(c.isspace() for c in TOKEN):
        raise SystemExit("TELEGRAM_BOT_TOKEN in .env contains a space. Copy it again from @BotFather.")

    builder = (
        Application.builder()
        .token(TOKEN)
        .concurrent_updates(True)
        .post_init(setup)
        .connect_timeout(20)
        .get_updates_connect_timeout(20)
    )
    if PROXY:
        # For networks that block Telegram, e.g. socks5://127.0.0.1:1080 or http://host:port
        builder = builder.proxy(PROXY).get_updates_proxy(PROXY)
    app = builder.build()
    app.add_handler(CommandHandler(["start", "help"], start, filters=AUTH))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("trends", trends, filters=AUTH, block=False))
    app.add_handler(CommandHandler("ideas", ideas, filters=AUTH, block=False))
    app.add_handler(CommandHandler("brief", brief, filters=AUTH, block=False))
    app.add_handler(CommandHandler("daily_on", daily_on, filters=AUTH))
    app.add_handler(CommandHandler("daily_off", daily_off, filters=AUTH))
    app.add_error_handler(on_error)

    log.info("GuidanceCast bot running. Press Ctrl+C to stop.")
    # Keep retrying on an unreliable connection instead of crashing at startup.
    app.run_polling(allowed_updates=Update.ALL_TYPES, bootstrap_retries=-1)


if __name__ == "__main__":
    main()
