import sqlite3
from twitchio.ext import commands
import time
import re


class Afk(commands.Cog):
    MESSAGE_COOLDOWN_SECONDS = 3

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_path = "afk.db"
        self._setup_database()
        self.last_afk_message_time = {}
        self.prefixes = self._get_prefixes()

    def _get_prefixes(self):
        """
        Retrieve the list of prefixes from the bot.
        If the bot has a 'prefix' attribute, use it.
        If not, check for '_prefix'.
        If neither exists, return a default prefix.
        """
        if hasattr(self.bot, "prefix"):
            prefix = self.bot.prefix
        elif hasattr(self.bot, "_prefix"):
            prefix = self.bot._prefix
        else:
            prefix = "#"

        # Ensure prefixes are in a list
        if isinstance(prefix, list):
            return prefix
        else:
            return [prefix]

    def _setup_database(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
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

            # Check if 'return_time' and 'active' columns exist, and add them if they don't
            cursor.execute("PRAGMA table_info(afk)")
            columns = [info[1] for info in cursor.fetchall()]
            if "return_time" not in columns:
                cursor.execute("ALTER TABLE afk ADD COLUMN return_time REAL")
            if "active" not in columns:
                cursor.execute("ALTER TABLE afk ADD COLUMN active INTEGER NOT NULL DEFAULT 1")

    @commands.command(name="afk", aliases=["sleep", "gn", "work", "food", "gaming", "bed"])
    async def afk_command(self, ctx: commands.Context, *, reason: str = None):
        user_id = ctx.author.id
        username = ctx.author.name

        # Extract the command used by parsing the message content with regex
        pattern = rf"^({'|'.join(re.escape(prefix) for prefix in self.prefixes)})(\w+)"
        match = re.match(pattern, ctx.message.content)
        if not match:
            await ctx.send(f"@{username}, please provide a reason for going AFK.")
            return

        command_used = match.group(2).lower()

        base_reason = {
            "afk": "AFK",
            "sleep": "sleeping",
            "gn": "sleeping",
            "bed": "sleeping",
            "work": "working",
            "food": "eating",
            "gaming": "gaming",
        }.get(
            command_used, "AFK"
        )  # Default to "AFK" if alias not found

        # Construct the full reason with user-provided details if any
        full_reason = f"{base_reason}: {reason}" if reason else base_reason

        afk_time = time.time()

        # Insert or update the AFK status in the database
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO afk (user_id, username, afk_time, reason, return_time, active)
                VALUES (?, ?, ?, ?, NULL, 1)
                ON CONFLICT(user_id) DO UPDATE SET
                    username=excluded.username,
                    afk_time=excluded.afk_time,
                    reason=excluded.reason,
                    return_time=NULL,
                    active=1
            """,
                (user_id, username, afk_time, full_reason),
            )

        await ctx.send(f"@{username} is now {full_reason}")

    @commands.command(name="rafk")
    async def rafk_command(self, ctx: commands.Context):
        """
        Resumes AFK status within 5 minutes of returning.
        Usage: #rafk
        """
        user_id = ctx.author.id
        username = ctx.author.name

        # Retrieve the user's AFK entry
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT afk_time, reason, return_time, active FROM afk WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()

            if row:
                afk_time, full_reason, return_time, active_status = row
                if active_status == 0 and return_time is not None:
                    time_since_return = time.time() - return_time
                    if time_since_return <= 5 * 60:  # 5 minutes
                        # Resume AFK
                        cursor.execute(
                            """
                            UPDATE afk
                            SET active = 1, return_time = NULL
                            WHERE user_id = ?
                        """,
                            (user_id,),
                        )
                        await ctx.send(f"@{username} has resumed {full_reason}")
                    else:
                        await ctx.send(
                            f"@{username}, it's been more than 5 minutes since you returned. Cannot resume AFK."
                        )
                else:
                    await ctx.send(f"@{username}, you are not eligible to resume AFK.")
            else:
                await ctx.send(f"@{username}, you have no AFK status to resume.")

    @commands.Cog.event()
    async def event_message(self, message):
        if message.echo or not message.channel:
            return

        if not message.author:
            self.log_missing_data(message)
            return

        user_id = message.author.id
        username = message.author.name

        # Prevent the cog from responding to its own messages
        if hasattr(self.bot, "bot_user_id") and message.author.id == self.bot.bot_user_id:
            return

        # Prevent responding to AFK commands themselves
        if self.is_afk_command(message):
            return

        self._handle_afk_return(message, user_id, username)

    def _handle_afk_return(self, message, user_id, username):
        """
        Handles the logic when a user returns from AFK.
        """
        # Check if the user is currently AFK
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT afk_time, reason, return_time, active FROM afk WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()

            if row:
                afk_time, full_reason, return_time, active_status = row

                if active_status == 1:
                    self._send_afk_return_message(message, user_id, username, afk_time, full_reason)
                    self._update_afk_status_inactive(user_id)
                elif return_time is not None:
                    time_since_return = time.time() - return_time
                    if time_since_return > 5 * 60:  # 5 minutes
                        self._remove_afk_entry(user_id)

    def _send_afk_return_message(self, message, user_id, username, afk_time, full_reason):
        """
        Sends the message indicating the user is no longer AFK.
        """
        afk_duration = time.time() - afk_time
        time_string = self.format_duration_string(afk_duration)

        # Parse the full_reason into base_reason and user_reason
        if ": " in full_reason:
            base_reason, user_reason = full_reason.split(": ", 1)
        else:
            base_reason = full_reason
            user_reason = None

        # Format the "no longer AFK" message based on whether a reason was provided
        no_longer_afk_message = (
            f"@{username} is no longer {base_reason}: {user_reason} ({time_string} ago)"
            if user_reason
            else f"@{username} is no longer {base_reason}. ({time_string} ago)"
        )

        # Check if a "no longer AFK" message was recently sent to prevent spamming
        if user_id in self.last_afk_message_time:
            time_since_last_message = time.time() - self.last_afk_message_time[user_id]
            if time_since_last_message < self.MESSAGE_COOLDOWN_SECONDS:
                return

        message.channel.send(no_longer_afk_message)
        self.last_afk_message_time[user_id] = time.time()

    def _update_afk_status_inactive(self, user_id):
        """
        Updates the AFK status to inactive in the database.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE afk
                SET active = 0, return_time = ?
                WHERE user_id = ?
            """,
                (time.time(), user_id),
            )

    def _remove_afk_entry(self, user_id):
        """
        Removes the AFK entry from the database if the user has been back for more than 5 minutes.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM afk WHERE user_id = ?", (user_id,))

    def is_afk_command(self, message):
        message_content = message.content.strip()
        pattern = rf"^({'|'.join(re.escape(prefix) for prefix in self.prefixes)})(\w+)"
        match = re.match(pattern, message_content)
        if match:
            command_used = match.group(2).lower()
            return command_used in ["afk", "sleep", "gn", "work", "food", "gaming", "bed", "rafk"]
        return False

    def format_duration_string(self, duration):
        """
        Takes a duration in seconds and returns a formatted string with non-zero components (days, hours, minutes, seconds)
        """
        days = int(duration // (24 * 3600))
        duration %= 24 * 3600
        hours = int(duration // 3600)
        duration %= 3600
        minutes = int(duration // 60)
        seconds = int(duration % 60)

        time_components = []
        if days > 0:
            time_components.append(f"{days}d")
        if hours > 0:
            time_components.append(f"{hours}h")
        if minutes > 0:
            time_components.append(f"{minutes}m")
        if seconds > 0:
            time_components.append(f"{seconds}s")

        return " ".join(time_components)

    def log_missing_data(self, message):
        # Implement logging for missing data if necessary
        self.bot.logger.warning(
            f"Received a message with missing data. Content: {getattr(message, 'content', 'None')}, "
            f"Channel: {getattr(message.channel, 'name', 'None')}"
        )


def prepare(bot):
    bot.add_cog(Afk(bot))
