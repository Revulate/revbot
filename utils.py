# utils.py

import re
import time
import logging
import sqlite3
from datetime import datetime, timezone, timedelta
from twitchio.ext import commands
from twitchio import PartialUser, Channel
from typing import List, Optional, Tuple
import asyncio

logger = logging.getLogger("twitch_bot.utils")


def split_message(message: str, max_length: int = 500) -> List[str]:
    """
    Splits a message into chunks of at most max_length characters,
    trying to split at sentence boundaries for better readability.

    Parameters:
        message (str): The message to split.
        max_length (int): Maximum length of each chunk.

    Returns:
        List[str]: A list of message chunks.
    """
    if len(message) <= max_length:
        return [message]

    sentences = re.findall(r"[^.!?]+[.!?]?", message)
    return _chunk_sentences(sentences, max_length)


def _chunk_sentences(sentences: List[str], max_length: int) -> List[str]:
    """
    Helper function to chunk sentences into smaller messages.

    Parameters:
        sentences (List[str]): The list of sentences to chunk.
        max_length (int): Maximum length of each chunk.

    Returns:
        List[str]: A list of message chunks.
    """
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
    """
    Helper function to split a long sentence into smaller parts.

    Parameters:
        sentence (str): The long sentence to split.
        max_length (int): Maximum length of each chunk.

    Returns:
        List[str]: A list of smaller sentence chunks.
    """
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
    """
    Removes duplicate sentences from the provided text.

    Parameters:
        text (str): The input text to remove duplicates from.

    Returns:
        str: Text with duplicate sentences removed.
    """
    sentences = re.split(r"(?<=[.!?]) +", text)
    seen, unique_sentences = set(), []

    for sentence in sentences:
        normalized = sentence.strip().lower()
        if normalized not in seen:
            unique_sentences.append(sentence.strip())
            seen.add(normalized)

    return " ".join(unique_sentences)


class CustomContext(commands.Context):
    """
    Custom Context class to override the send method for message splitting
    and rate limiting.
    """

    async def send(self, content: str = None, **kwargs):
        """
        Overrides the default send method to handle message chunking and rate limiting.

        Parameters:
            content (str): The message content to send.
            **kwargs: Additional keyword arguments for the send method.
        """
        if content:
            chunks = split_message(content)
            for chunk in chunks:
                await super().send(chunk, **kwargs)
                await asyncio.sleep(1)  # Rate limit


async def fetch_user(bot: commands.Bot, user_identifier: str) -> Optional[PartialUser]:
    """
    Fetches a user by name or ID.

    Parameters:
        bot (commands.Bot): The bot instance.
        user_identifier (str): The username (with or without @) or user ID.

    Returns:
        Optional[PartialUser]: The user object if found, else None.
    """
    try:
        user_identifier = user_identifier.lstrip("@")
        users = (
            await bot.fetch_users(ids=[user_identifier])
            if user_identifier.isdigit()
            else await bot.fetch_users(names=[user_identifier])
        )
        return users[0] if users else None
    except Exception as e:
        logger.error(f"Error fetching user '{user_identifier}': {e}")
        return None


def get_channel(bot: commands.Bot, channel_name: str) -> Optional[Channel]:
    """
    Retrieves a channel object by name.

    Parameters:
        bot (commands.Bot): The bot instance.
        channel_name (str): The name of the channel.

    Returns:
        Optional[Channel]: The channel object if found, else None.
    """
    channel = bot.get_channel(channel_name)
    if not channel:
        logger.warning(f"Channel '{channel_name}' not found in bot's connected channels.")
    return channel


def expand_time_units(time_str: str) -> str:
    """
    Inserts spaces between numbers and letters if needed.

    Parameters:
        time_str (str): The time string to expand.

    Returns:
        str: The time string with spaces inserted.
    """
    return re.sub(r"(\d)([a-zA-Z])", r"\1 \2", time_str)


def parse_time_string(time_str: str) -> Optional[timedelta]:
    """
    Parses a time duration string into a timedelta.

    Args:
        time_str (str): The time duration string.

    Returns:
        Optional[timedelta]: The parsed time duration or None if parsing fails.
    """
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
    """
    Parses the command arguments to extract time and message.

    Parameters:
        args (List[str]): The list of arguments from the command.
        expect_time_keyword_at_start (bool): Whether to expect a time keyword at the start.

    Returns:
        Tuple[Optional[datetime], str]: A tuple containing the remind_time (datetime or None) and the message.
    """
    from dateparser import parse

    time_keywords = ["in", "on", "after"]
    # time_keyword = None
    time_index = -1

    if expect_time_keyword_at_start and args and args[0].lower() in time_keywords:
        # time_keyword = args[0].lower()
        time_index = 0
    else:
        message_text = " ".join(args).strip()
        if message_text:
            return None, message_text
        else:
            return False, "Please provide a message for the reminder."

    if time_index + 1 >= len(args):
        return False, "Please provide a time after the keyword."

    for i in range(time_index + 2, len(args) + 1):
        time_str = " ".join(args[time_index + 1 : i])
        message_text = " ".join(args[i:]).strip()
        time_str_expanded = expand_time_units(time_str)
        if not time_str_expanded:
            continue
        delta = parse_time_string(time_str_expanded)
        if delta:
            remind_time = datetime.now(timezone.utc) + delta
            if message_text:
                return remind_time, message_text
            else:
                continue
        if any(c.isalpha() or c in ("/", "-") for c in time_str_expanded):
            remind_time = parse(
                time_str_expanded,
                settings={
                    "TIMEZONE": "UTC",
                    "RETURN_AS_TIMEZONE_AWARE": True,
                    "PREFER_DATES_FROM": "future",
                    "RELATIVE_BASE": datetime.now(timezone.utc),
                },
            )
            if remind_time:
                if message_text:
                    return remind_time, message_text
                else:
                    continue
    return False, "Could not parse the time specified."


def format_time_delta(delta: timedelta) -> str:
    """
    Formats a timedelta into a human-readable string with multiple units.

    Args:
        delta (timedelta): The time difference.

    Returns:
        str: Formatted time difference.
    """
    total_seconds = int(delta.total_seconds())
    periods = [("d", 86400), ("h", 3600), ("m", 60), ("s", 1)]
    return " ".join(f"{value}{name}" for name, seconds in periods if (value := total_seconds // seconds)) or "0s"


def format_duration(seconds):
    """Formats the duration from seconds to a human-readable string."""
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
    """Calculates the AFK duration in seconds."""
    return time.time() - start_time


def get_database_connection(db_path="reminders.db") -> sqlite3.Connection:
    """
    Establishes a connection to the SQLite database.

    Parameters:
        db_path (str): Path to the SQLite database file.

    Returns:
        sqlite3.Connection: The database connection object.
    """
    return sqlite3.connect(db_path)


def setup_database(db_path="reminders.db"):
    """
    Sets up the reminders database with the necessary tables.

    Parameters:
        db_path (str): Path to the SQLite database file.
    """
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
        cursor.execute("PRAGMA table_info(reminders)")
        if "created_at" not in [info[1] for info in cursor.fetchall()]:
            cursor.execute(
                "ALTER TABLE reminders ADD COLUMN created_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00+00:00'"
            )


def remove_reminder(reminder_id: str, db_path="reminders.db"):
    """
    Removes a reminder from the database.

    Parameters:
        reminder_id (str): The ID of the reminder to remove.
        db_path (str): Path to the SQLite database file.
    """
    with get_database_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        conn.commit()


# DnD Database Setup
def setup_dnd_database(db_path="twitch_bot.db"):
    """
    Sets up the DnD-related tables in the database.

    Parameters:
        db_path (str): Path to the SQLite database file.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create game_users table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS game_users (
            user_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            race TEXT NOT NULL,
            character_class TEXT NOT NULL,
            background TEXT NOT NULL,
            level INTEGER DEFAULT 1,
            experience INTEGER DEFAULT 0,
            strength INTEGER,
            intelligence INTEGER,
            dexterity INTEGER,
            constitution INTEGER,
            wisdom INTEGER,
            charisma INTEGER,
            skills TEXT, -- JSON string
            gear TEXT -- JSON string
        )
    """
    )

    # Create items table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS items (
            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL, -- weapon, armor, etc.
            stats TEXT, -- JSON string
            rarity TEXT NOT NULL
        )
    """
    )

    # Create quests table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS quests (
            quest_id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL,
            difficulty TEXT NOT NULL,
            rewards TEXT, -- JSON string
            requirements TEXT -- JSON string
        )
    """
    )

    # Create combat table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS combat (
            combat_id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_ids TEXT NOT NULL, -- JSON array of user_ids
            status TEXT NOT NULL, -- ongoing, completed
            log TEXT -- JSON string
        )
    """
    )

    # Create duels table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS duels (
            duel_id INTEGER PRIMARY KEY AUTOINCREMENT,
            challenger_id TEXT NOT NULL,
            opponent_id TEXT NOT NULL,
            status TEXT NOT NULL, -- ongoing, completed
            log TEXT -- JSON string
        )
    """
    )

    # Create parties table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS parties (
            party_id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_ids TEXT NOT NULL, -- JSON array of user_ids
            status TEXT NOT NULL -- active, disbanded
        )
    """
    )

    conn.commit()
    conn.close()
    logger.debug("DnD database setup completed.")


# Call the setup functions when the module is imported
setup_database()
setup_dnd_database()
