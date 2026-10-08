"""Trend analysis for GuidanceCast using the free tier of Google's Gemini API."""

import json
import logging
import os
import re
from datetime import date
from pathlib import Path

from google import genai
from google.genai import errors, types

import sources

log = logging.getLogger(__name__)

# Free-tier models, tried in order. If one is rate-limited or retired, the next is used.
MODELS = [m.strip() for m in os.getenv("GEMINI_MODELS", "gemini-3.5-flash,gemini-2.5-flash").split(",") if m.strip()]
HISTORY_FILE = Path(__file__).parent / "data" / "history.json"

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

SYSTEM_PROMPT = """You are a research assistant for the producer of the GuidanceCast Podcast, \
an Islamic podcast for Muslims living in the West (UK, USA, Canada, Australia, Ireland and \
Western Europe). Your job is to spot what Western Muslims are talking about right now and turn \
it into strong podcast episode ideas.

You will be given a list of recent headlines and online discussions gathered from Google News, \
Muslim media outlets and Muslim communities on Reddit. Work only from that material: group \
related items into topics, judge how hot each topic is by how many sources and regions mention \
it, and cite the links provided. Do not invent events, statistics or quotes. Ignore items that \
are not relevant to Western Muslims.

If a topic is sensitive (sectarian, political, or legally risky), say so briefly and suggest a \
responsible angle. Keep advice consistent with mainstream Islamic scholarship and suggest \
qualified guests (scholars, counsellors, specialists) where a topic needs them. Evergreen themes \
(marriage, family, faith and doubt, mental health, careers, halal finance, converts, identity, \
upcoming Islamic dates) are welcome when the material gives them a fresh hook.

Format your reply for Telegram using ONLY these HTML tags: <b>, <i>, <a href="...">. \
Do not use Markdown, # headings, asterisks, tables or any other tags. Use plain line breaks, \
emoji bullets and short paragraphs so it is easy to read on a phone.

At the very end, add one final line that starts with TITLES: followed by the names of every \
topic and episode you covered, separated by " | ". This line is removed before the producer \
sees it."""


class ResearchError(Exception):
    """Raised with a message that is safe to show in Telegram."""


def _load_history() -> list[str]:
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_history(entries: list[str]) -> None:
    history = (_load_history() + entries)[-40:]
    HISTORY_FILE.parent.mkdir(exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")


def _history_note() -> str:
    history = _load_history()
    if not history:
        return ""
    recent = "\n".join(f"- {h}" for h in history[-20:])
    return (
        "\n\nThese topics were already covered in recent briefings. Only repeat one if "
        f"the material shows a genuinely new development:\n{recent}"
    )


async def _generate(prompt: str) -> str:
    last_error = None
    for model in MODELS:
        try:
            response = await client.aio.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
            )
        except errors.APIError as e:
            # 429 = free-tier quota used up, 404 = model retired: try the next model.
            log.warning("Gemini model %s failed (%s): %s", model, e.code, e.message)
            last_error = e
            continue
        if response.text:
            return response.text
    if last_error is not None and last_error.code == 429:
        raise ResearchError("⏳ The free Gemini quota is used up for now. Try again later.")
    if last_error is not None and last_error.code in (400, 401, 403):
        raise ResearchError("⚠️ Gemini rejected the request. Check GEMINI_API_KEY in .env.")
    raise ResearchError("⚠️ Gemini didn't return an answer. Please try again in a few minutes.")


async def _run(task: str) -> str:
    items = await sources.gather()
    if not items:
        raise ResearchError("⚠️ Couldn't load any news or Reddit feeds. Check the internet connection.")
    today = date.today().strftime("%A %d %B %Y")
    prompt = (
        f"Today is {today}.\n\n{task}{_history_note()}\n\n"
        f"Material gathered in the last few days ({len(items)} items):\n\n{sources.format_items(items)}"
    )
    text = await _generate(prompt)

    match = re.search(r"^\s*TITLES:(.*)$", text, flags=re.MULTILINE)
    if match:
        _save_history([t.strip() for t in match.group(1).split("|") if t.strip()])
        text = text[: match.start()]
    return text.strip()


async def hot_topics() -> str:
    return await _run(
        "Find the 6-8 hottest topics in the Western Muslim world right now.\n\n"
        "For each topic give:\n"
        "🔥 <b>Topic name</b>\n"
        "Why it's trending (2-3 sentences, mentioning which regions and communities are discussing it)\n"
        "Heat: 🔥 to 🔥🔥🔥\n"
        "Sources: 1-3 links from the material\n\n"
        "Finish with one line naming the single topic you would record an episode on this week."
    )


async def podcast_ideas(focus: str | None = None) -> str:
    scope = (
        f"The producer wants episodes about: {focus}. Use any related material below, and "
        "if little is directly related, build ideas on the closest current hooks you can find."
        if focus
        else "Pick the strongest current topics from the material."
    )
    return await _run(
        f"{scope}\n\n"
        "Suggest 5 GuidanceCast episode ideas. For each give:\n"
        "🎙 <b>Episode title</b> (catchy, under 10 words)\n"
        "<i>Hook:</i> why listeners care this week\n"
        "<i>Angle:</i> the episode's take or central question\n"
        "<i>Talking points:</i> 3-4 short bullets\n"
        "<i>Guest ideas:</i> types of guests or named public figures who speak on this\n"
        "<i>Clip idea:</i> one short-form social clip to promote it\n"
        "Sources: 1-2 links from the material"
    )


async def weekly_brief() -> str:
    return await _run(
        "Write the producer's briefing.\n\n"
        "Part 1 - <b>What's hot</b>: the top 5 topics in the Western Muslim world, each with "
        "2 sentences on why, a heat rating (🔥 to 🔥🔥🔥) and a source link.\n"
        "Part 2 - <b>Episode ideas</b>: 3 episode pitches built on those topics, each with "
        "title, hook, angle, 3 talking points and guest ideas.\n"
        "Part 3 - <b>Coming up</b>: dates in the next 2-4 weeks worth planning for (Islamic "
        "calendar dates you are confident about, plus anything upcoming mentioned in the material)."
    )
