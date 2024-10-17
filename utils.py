import re
import time
import logging
from datetime import datetime, timezone, timedelta
from twitchio.ext import commands
from twitchio import PartialUser, Channel
from typing import List, Optional, Tuple
import sys
import os
import sqlite3
import validators
from logger import log_info, log_error, log_warning, log_debug, get_logger

logger = get_logger("twitch_bot.utils")

# Add the virtual environment's site-packages to sys.path
venv_path = os.getenv("PYTHONPATH")
if venv_path:
    sys.path.append(venv_path)


def normalize_username(username: str) -> str:
    return username.lstrip("@")


def split_message(message: str, max_length: int = 500) -> List[str]:
    if len(message) <= max_length:
        return [message]

    sentences = re.findall(r"[^.!?]+[.!?]?", message)
    return _chunk_sentences(sentences, max_length)


def _chunk_sentences(sentences: List[str], max_length: int) -> List[str]:
    messages, current_chunk = [], ""

    for sentence in sentences:
        sentence = sentence.strip()
        if len(current_chunk) + len(sentence) + 1 > max_length:
            if current_chunk:
                messages.append(current_chunk)
            current_chunk = sentence if len(sentence) <= max_length else ""
            if len(sentence) > max_length:
                messages.extend(_split_long_sentence(sentence, max_length))
        else:
            current_chunk += (" " + sentence) if current_chunk else sentence

    if current_chunk:
        messages.append(current_chunk)
    return messages


def _split_long_sentence(sentence: str, max_length: int) -> List[str]:
    words = sentence.split()
    sub_chunks, current_chunk = [], ""

    for word in words:
        if len(current_chunk) + len(word) + 1 > max_length:
            sub_chunks.append(current_chunk)
            current_chunk = word
        else:
            current_chunk += (" " + word) if current_chunk else word

    if current_chunk:
        sub_chunks.append(current_chunk)
    return sub_chunks


def remove_duplicate_sentences(text: str) -> str:
    sentences = re.split(r"(?<=[.!?]) +", text)
    seen, unique_sentences = set(), []

    for sentence in sentences:
        normalized = sentence.strip().lower()
        if normalized not in seen:
            unique_sentences.append(sentence.strip())
            seen.add(normalized)

    return " ".join(unique_sentences)


async def fetch_user(bot: commands.Bot, user_identifier: str) -> Optional[PartialUser]:
    try:
        user_identifier = user_identifier.lstrip("@")
        users = (
            await bot.fetch_users(ids=[user_identifier])
            if user_identifier.isdigit()
            else await bot.fetch_users(names=[user_identifier])
        )
        return users[0] if users else None
    except Exception as e:
        log_error(f"Error fetching user '{user_identifier}': {e}")
        return None


def get_channel(bot: commands.Bot, channel_name: str) -> Optional[Channel]:
    channel = bot.get_channel(channel_name)
    if not channel:
        log_warning(f"Channel '{channel_name}' not found in bot's connected channels.")
    return channel


def expand_time_units(time_str: str) -> str:
    return re.sub(r"(\d)([a-zA-Z])", r"\1 \2", time_str)


def parse_time_string(time_str: str) -> Optional[timedelta]:
    time_str = time_str.lower().replace(",", " ").replace("and", " ").replace("-", " ")
    pattern = r"(?P<value>\d+(\.\d+)?)\s*(?P<unit>[a-zA-Z]+)"
    matches = re.finditer(pattern, time_str)
    kwargs = {}
    unit_map = {
        "second": "seconds",
        "sec": "seconds",
        "s": "seconds",
        "minute": "minutes",
        "min": "minutes",
        "m": "minutes",
        "hour": "hours",
        "h": "hours",
        "day": "days",
        "d": "days",
        "week": "weeks",
        "w": "weeks",
        "month": "days",
        "year": "days",
        "y": "days",
    }
    for match in matches:
        value, unit = float(match.group("value")), match.group("unit")
        key = next((v for k, v in unit_map.items() if unit.startswith(k)), None)
        if key:
            kwargs.setdefault(key, 0)
            kwargs[key] += value * (30 if unit == "month" else 365 if unit == "year" else 1)
    return timedelta(**kwargs) if kwargs else None


def parse_time(args: List[str], expect_time_keyword_at_start: bool = True) -> Tuple[Optional[datetime], str]:
    from dateparser import parse

    time_keywords = ["in", "on", "after"]
    time_str = " ".join(args)
    message = ""

    if expect_time_keyword_at_start and args and args[0].lower() in time_keywords:
        time_str = " ".join(args[1:])
    else:
        return None, time_str

    for i in range(len(args), 0, -1):
        time_part = " ".join(args[:i])
        message = " ".join(args[i:])

        delta = parse_time_string(time_part)
        if delta:
            return datetime.now(timezone.utc) + delta, message

        parsed_time = parse(
            time_part,
            settings={
                "TIMEZONE": "UTC",
                "RETURN_AS_TIMEZONE_AWARE": True,
                "PREFER_DATES_FROM": "future",
                "RELATIVE_BASE": datetime.now(timezone.utc),
            },
        )
        if parsed_time:
            return parsed_time, message

    return False, "Could not parse the time specified."


def format_time_delta(delta: timedelta) -> str:
    total_seconds = int(delta.total_seconds())
    periods = [("d", 86400), ("h", 3600), ("m", 60), ("s", 1)]
    return " ".join(f"{value}{name}" for name, seconds in periods if (value := total_seconds // seconds)) or "0s"


def format_duration(seconds):
    seconds = int(seconds)
    weeks, remainder = divmod(seconds, 604800)
    days, remainder = divmod(remainder, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts = []
    for value, unit in [(weeks, "w"), (days, "d"), (hours, "h"), (minutes, "m"), (seconds, "s")]:
        if value:
            parts.append(f"{value}{unit}")
    return " ".join(parts) or "0s"


def get_afk_duration(start_time):
    return time.time() - start_time


def get_database_connection(db_path="bot.db") -> sqlite3.Connection:
    return sqlite3.connect(db_path)


def setup_database(db_path="bot.db"):
    with get_database_connection(db_path) as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                target_id INTEGER NOT NULL,
                target_name TEXT NOT NULL,
                channel_id INTEGER NOT NULL,
                channel_name TEXT NOT NULL,
                message TEXT NOT NULL,
                remind_time TEXT,
                private INTEGER NOT NULL,
                trigger_on_message INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_stats (
                user_id TEXT PRIMARY KEY,
                username TEXT,
                message_count INTEGER DEFAULT 0,
                first_seen TIMESTAMP,
                last_seen TIMESTAMP
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS afk (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                afk_time REAL NOT NULL,
                reason TEXT,
                return_time REAL,
                active INTEGER NOT NULL DEFAULT 1
            )
        """
        )

        conn.commit()


def is_valid_url(url: str) -> bool:
    return validators.url(url)


def format_time_ago(timestamp: datetime) -> str:
    now = datetime.now(timezone.utc)
    delta = now - timestamp
    if delta.days > 365:
        return f"{delta.days // 365} year{'s' if delta.days // 365 != 1 else ''} ago"
    elif delta.days > 30:
        return f"{delta.days // 30} month{'s' if delta.days // 30 != 1 else ''} ago"
    elif delta.days > 0:
        return f"{delta.days} day{'s' if delta.days != 1 else ''} ago"
    elif delta.seconds > 3600:
        return f"{delta.seconds // 3600} hour{'s' if delta.seconds // 3600 != 1 else ''} ago"
    elif delta.seconds > 60:
        return f"{delta.seconds // 60} minute{'s' if delta.seconds // 60 != 1 else ''} ago"
    else:
        return f"{delta.seconds} second{'s' if delta.seconds != 1 else ''} ago"
