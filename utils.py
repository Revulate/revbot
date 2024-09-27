# utils.py
import re
import logging
import sqlite3
from datetime import datetime, timezone, timedelta
from twitchio.ext import commands

logger = logging.getLogger('twitch_bot.utils')


def split_message(message: str, max_length: int = 500) -> list:
    """
    Splits a message into chunks that fit within the specified max_length.
    Ensures that words are not split and accounts for an optional prefix.
    """
    words = message.split()
    chunks = []
    current_chunk = ""

    for word in words:
        # Check if adding the next word exceeds max_length
        if len(current_chunk) + len(word) + 1 <= max_length:
            if current_chunk:
                current_chunk += " " + word
            else:
                current_chunk = word
        else:
            # Save the current chunk and start a new one
            chunks.append(current_chunk)
            current_chunk = word

    # Append the last chunk if not empty
    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def remove_duplicate_sentences(text: str) -> str:
    """
    Removes duplicate sentences from the provided text.

    Parameters:
        text (str): The input text to remove duplicates from.

    Returns:
        str: Text with duplicate sentences removed.
    """
    # Split the text into sentences based on punctuation followed by spaces
    sentences = re.split(r'(?<=[.!?]) +', text)
    seen = set()
    unique_sentences = []

    for sentence in sentences:
        # Normalize by stripping extra spaces and lowercasing
        normalized = sentence.strip().lower()

        # Only add sentence if it hasn't been seen before
        if normalized not in seen:
            unique_sentences.append(sentence.strip())
            seen.add(normalized)

    # Return the text with unique sentences only
    return ' '.join(unique_sentences)


async def fetch_user(bot: commands.Bot, user_identifier):
    """
    Fetches a user by name or ID.
    """
    try:
        if isinstance(user_identifier, int) or user_identifier.isdigit():
            users = await bot.fetch_users(ids=[str(user_identifier)])
        else:
            users = await bot.fetch_users(names=[user_identifier.lstrip('@')])
        if users:
            return users[0]
        else:
            logger.error(f"User '{user_identifier}' not found.")
            return None
    except Exception as e:
        logger.error(f"Error fetching user '{user_identifier}': {e}")
        return None


def get_channel(bot: commands.Bot, channel_name):
    """
    Retrieves a channel object by name.
    """
    channel = bot.get_channel(channel_name)
    if channel:
        return channel
    else:
        logger.warning(f"Channel '{channel_name}' not found in bot's connected channels.")
        return None


def expand_time_units(time_str):
    """
    Inserts spaces between numbers and letters if needed.
    """
    # Insert spaces between numbers and letters
    time_str = re.sub(r'(\d)([a-zA-Z])', r'\1 \2', time_str)
    return time_str


def parse_time_string(time_str):
    """
    Parses a time duration string into a timedelta.

    Args:
        time_str (str): The time duration string.

    Returns:
        timedelta: The parsed time duration.
    """
    time_str = time_str.lower()
    # Remove any commas or 'and'
    time_str = time_str.replace(',', ' ').replace('and', ' ').replace('-', ' ')
    # Regex to find all occurrences of number + unit
    pattern = r'(?P<value>\d+(\.\d+)?)\s*(?P<unit>[a-zA-Z]+)'
    matches = re.finditer(pattern, time_str)
    kwargs = {}
    for match in matches:
        value = float(match.group('value'))
        unit = match.group('unit')
        if unit.startswith(('second', 'sec', 's')):
            kwargs.setdefault('seconds', 0)
            kwargs['seconds'] += value
        elif unit.startswith(('minute', 'min', 'm')):
            kwargs.setdefault('minutes', 0)
            kwargs['minutes'] += value
        elif unit.startswith(('hour', 'h')):
            kwargs.setdefault('hours', 0)
            kwargs['hours'] += value
        elif unit.startswith(('day', 'd')):
            kwargs.setdefault('days', 0)
            kwargs['days'] += value
        elif unit.startswith(('week', 'w')):
            kwargs.setdefault('weeks', 0)
            kwargs['weeks'] += value
        elif unit.startswith(('month',)):
            # Approximate months as 30 days
            kwargs.setdefault('days', 0)
            kwargs['days'] += value * 30
        elif unit.startswith(('year', 'y')):
            # Approximate years as 365 days
            kwargs.setdefault('days', 0)
            kwargs['days'] += value * 365
    if kwargs:
        return timedelta(**kwargs)
    else:
        return None


def parse_time(args, expect_time_keyword_at_start=True):
    """
    Parses the command arguments to extract time and message.

    Returns:
        tuple: (remind_time (datetime or None), message (str) or error message)
    """
    from dateparser import parse

    time_keywords = ['in', 'on', 'after']
    time_keyword = None
    time_index = -1

    # If time keyword is at the expected position
    if expect_time_keyword_at_start and args and args[0].lower() in time_keywords:
        time_keyword = args[0].lower()
        time_index = 0
    else:
        # No time keyword at the expected position
        # Treat the entire message as the reminder text
        message_text = ' '.join(args).strip()
        if message_text:
            return None, message_text
        else:
            return False, "Please provide a message for the reminder."

    if time_index + 1 >= len(args):
        return False, "Please provide a time after the keyword."

    # Build time_str from the arguments after the time keyword
    # Try to find where the time expression ends and the message begins
    for i in range(time_index + 1, len(args) + 1):
        time_str = ' '.join(args[time_index + 1:i])
        time_str_expanded = expand_time_units(time_str)
        delta = parse_time_string(time_str_expanded)
        if delta:
            remind_time = datetime.now(timezone.utc) + delta
            # The rest of the args from i onwards are the message
            message_text = ' '.join(args[i:]).strip()
            if message_text:
                return remind_time, message_text
            else:
                return False, "Please provide a message for the reminder."
        else:
            # Try parsing as date
            remind_time = parse(time_str_expanded, settings={
                'TIMEZONE': 'UTC',
                'RETURN_AS_TIMEZONE_AWARE': True,
                'PREFER_DATES_FROM': 'future',
                'RELATIVE_BASE': datetime.now(timezone.utc)
            })
            if remind_time:
                message_text = ' '.join(args[i:]).strip()
                if message_text:
                    return remind_time, message_text
                else:
                    return False, "Please provide a message for the reminder."
    # If we get here, time parsing failed
    return False, "Could not parse the time specified."


def format_time_delta(delta):
    """
    Formats a timedelta into a human-readable string with multiple units.

    Args:
        delta (timedelta): The time difference.

    Returns:
        str: Formatted time difference.
    """
    total_seconds = int(delta.total_seconds())
    periods = [
        ('d', 86400),  # 60 * 60 * 24
        ('h', 3600),
        ('m', 60),
        ('s', 1),
    ]

    strings = []
    for period_name, period_seconds in periods:
        if total_seconds >= period_seconds:
            period_value, total_seconds = divmod(total_seconds, period_seconds)
            strings.append(f"{int(period_value)}{period_name}")
    if not strings:
        return '0s'
    return ' '.join(strings)


# Database functions
def get_database_connection(db_path='reminders.db'):
    return sqlite3.connect(db_path)


def setup_database(db_path='reminders.db'):
    """Sets up the reminders database."""
    conn = get_database_connection(db_path)
    cursor = conn.cursor()
    cursor.execute('''
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
            active INTEGER NOT NULL DEFAULT 1
        )
    ''')
    conn.commit()
    conn.close()
    logger.debug("Reminders database setup completed.")


def remove_reminder(reminder_id, db_path='reminders.db'):
    """Removes a reminder from the database."""
    conn = get_database_connection(db_path)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM reminders WHERE id = ?', (reminder_id,))
    conn.commit()
    conn.close()
    logger.debug(f"Removed reminder {reminder_id} from database.")
