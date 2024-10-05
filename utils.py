# utils.py

import re
import logging
import sqlite3
from datetime import datetime, timezone, timedelta
from twitchio.ext import commands
from twitchio import PartialUser, Channel  # Correct imports for PartialUser and Channel
from typing import List, Optional, Tuple
import asyncio

logger = logging.getLogger('twitch_bot.utils')


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
    # Ensure that the message is a string
    if not isinstance(message, str):
        message = str(message)

    # List to hold the message chunks
    messages = []

    # If the message is already short enough, return it as the only element
    if len(message) <= max_length:
        return [message]

    # Split the message into sentences using regex
    sentences = re.findall(r'[^.!?]+[.!?]?', message)

    current_chunk = ''
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        # If adding the sentence would exceed the max_length, start a new chunk
        if len(current_chunk) + len(sentence) + 1 > max_length:
            if current_chunk:
                messages.append(current_chunk.strip())
            if len(sentence) > max_length:
                # If the sentence itself is longer than max_length, split it further
                words = sentence.split()
                sub_chunk = ''
                for word in words:
                    if len(sub_chunk) + len(word) + 1 > max_length:
                        messages.append(sub_chunk.strip())
                        sub_chunk = word
                    else:
                        sub_chunk += ' ' + word if sub_chunk else word
                if sub_chunk:
                    messages.append(sub_chunk.strip())
                current_chunk = ''
            else:
                current_chunk = sentence
        else:
            current_chunk += ' ' + sentence if current_chunk else sentence

    # Add any remaining text
    if current_chunk:
        messages.append(current_chunk.strip())

    return messages


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
        max_length = 500  # Twitch message length limit

        if content is None:
            return await super().send(content, **kwargs)

        # Split the message into chunks
        chunks = split_message(content, max_length=max_length)

        for chunk in chunks:
            try:
                await super().send(chunk, **kwargs)
                # Add delay between messages to comply with rate limits
                await asyncio.sleep(1)  # Adjust delay as needed
            except Exception as e:
                logger.error(f"Error sending message chunk: {e}", exc_info=True)


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
        if user_identifier.startswith('@'):
            user_identifier = user_identifier[1:]
        if user_identifier.isdigit():
            users = await bot.fetch_users(ids=[user_identifier])
        else:
            users = await bot.fetch_users(names=[user_identifier])
        if users:
            return users[0]
        else:
            logger.error(f"User '{user_identifier}' not found.")
            return None
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
    if channel:
        return channel
    else:
        logger.warning(f"Channel '{channel_name}' not found in bot's connected channels.")
        return None


def expand_time_units(time_str: str) -> str:
    """
    Inserts spaces between numbers and letters if needed.

    Parameters:
        time_str (str): The time string to expand.

    Returns:
        str: The time string with spaces inserted.
    """
    # Insert spaces between numbers and letters
    time_str = re.sub(r'(\d)([a-zA-Z])', r'\1 \2', time_str)
    return time_str


def parse_time_string(time_str: str) -> Optional[timedelta]:
    """
    Parses a time duration string into a timedelta.

    Args:
        time_str (str): The time duration string.

    Returns:
        Optional[timedelta]: The parsed time duration or None if parsing fails.
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
    # Try to find the shortest possible time expression
    for i in range(time_index + 2, len(args) + 1):
        time_str = ' '.join(args[time_index + 1:i])
        message_text = ' '.join(args[i:]).strip()
        time_str_expanded = expand_time_units(time_str)
        if not time_str_expanded:
            continue  # Skip if time_str is empty
        # Attempt to parse as a timedelta
        delta = parse_time_string(time_str_expanded)
        if delta:
            remind_time = datetime.now(timezone.utc) + delta
            if message_text:
                return remind_time, message_text
            else:
                continue  # Try to find a longer time_str to get a message
        else:
            # Avoid parsing single numbers as dates
            if time_str_expanded.isdigit():
                continue  # Skip parsing this time_str
            # Only try dateparser.parse if time_str contains letters or slashes
            if any(c.isalpha() or c in ('/', '-') for c in time_str_expanded):
                # Try parsing as date
                remind_time = parse(time_str_expanded, settings={
                    'TIMEZONE': 'UTC',
                    'RETURN_AS_TIMEZONE_AWARE': True,
                    'PREFER_DATES_FROM': 'future',
                    'RELATIVE_BASE': datetime.now(timezone.utc)
                })
                if remind_time:
                    if message_text:
                        return remind_time, message_text
                    else:
                        continue  # Try a longer time_str
    # If we get here, time parsing failed
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
def get_database_connection(db_path='reminders.db') -> sqlite3.Connection:
    """
    Establishes a connection to the SQLite database.

    Parameters:
        db_path (str): Path to the SQLite database file.

    Returns:
        sqlite3.Connection: The database connection object.
    """
    return sqlite3.connect(db_path)


def setup_database(db_path='reminders.db'):
    """
    Sets up the reminders database with the necessary tables.

    Parameters:
        db_path (str): Path to the SQLite database file.
    """
    conn = get_database_connection(db_path)
    cursor = conn.cursor()
    # Create the table with the new 'created_at' column
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
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
    ''')
    # Check if 'created_at' column exists; if not, add it
    cursor.execute("PRAGMA table_info(reminders)")
    columns = [info[1] for info in cursor.fetchall()]
    if 'created_at' not in columns:
        cursor.execute("ALTER TABLE reminders ADD COLUMN created_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00+00:00'")
        logger.debug("Added 'created_at' column to 'reminders' table.")
    conn.commit()
    conn.close()
    logger.debug("Reminders database setup completed.")


def remove_reminder(reminder_id: str, db_path='reminders.db'):
    """
    Removes a reminder from the database.

    Parameters:
        reminder_id (str): The ID of the reminder to remove.
        db_path (str): Path to the SQLite database file.
    """
    conn = get_database_connection(db_path)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM reminders WHERE id = ?', (reminder_id,))
    conn.commit()
    conn.close()
    logger.debug(f"Removed reminder {reminder_id} from database.")


# DnD Database Setup
def setup_dnd_database(db_path='twitch_bot.db'):
    """
    Sets up the DnD-related tables in the database.

    Parameters:
        db_path (str): Path to the SQLite database file.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create game_users table
    cursor.execute('''
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
    ''')

    # Create items table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS items (
            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL, -- weapon, armor, etc.
            stats TEXT, -- JSON string
            rarity TEXT NOT NULL
        )
    ''')

    # Create quests table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS quests (
            quest_id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL,
            difficulty TEXT NOT NULL,
            rewards TEXT, -- JSON string
            requirements TEXT -- JSON string
        )
    ''')

    # Create combat table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS combat (
            combat_id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_ids TEXT NOT NULL, -- JSON array of user_ids
            status TEXT NOT NULL, -- ongoing, completed
            log TEXT -- JSON string
        )
    ''')

    # Create duels table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS duels (
            duel_id INTEGER PRIMARY KEY AUTOINCREMENT,
            challenger_id TEXT NOT NULL,
            opponent_id TEXT NOT NULL,
            status TEXT NOT NULL, -- ongoing, completed
            log TEXT -- JSON string
        )
    ''')

    # Create parties table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS parties (
            party_id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_ids TEXT NOT NULL, -- JSON array of user_ids
            status TEXT NOT NULL -- active, disbanded
        )
    ''')

    conn.commit()
    conn.close()
    logger.debug("DnD database setup completed.")


# Call the setup functions when the module is imported
setup_database()
setup_dnd_database()
