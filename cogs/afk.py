import sqlite3
from twitchio.ext import commands
import time

class Afk(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_path = 'afk.db'
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
        if hasattr(self.bot, 'prefix'):
            prefix = self.bot.prefix
        elif hasattr(self.bot, '_prefix'):
            prefix = self.bot._prefix
        else:
            prefix = '#'

        # Ensure prefixes are in a list
        if isinstance(prefix, list):
            return prefix
        else:
            return [prefix]

    def _setup_database(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS afk (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                afk_time REAL NOT NULL,
                reason TEXT,
                return_time REAL,
                active INTEGER NOT NULL DEFAULT 1
            )
        ''')

        # Check if 'return_time' and 'active' columns exist, and add them if they don't
        cursor.execute("PRAGMA table_info(afk)")
        columns = [info[1] for info in cursor.fetchall()]
        if 'return_time' not in columns:
            cursor.execute("ALTER TABLE afk ADD COLUMN return_time REAL")
        if 'active' not in columns:
            cursor.execute("ALTER TABLE afk ADD COLUMN active INTEGER NOT NULL DEFAULT 1")

        conn.commit()
        conn.close()

    @commands.command(name="afk", aliases=["sleep", "gn", "work", "food", "gaming", "bed"])
    async def afk_command(self, ctx: commands.Context, *, reason: str = None):
        user_id = ctx.author.id
        username = ctx.author.name

        # Determine the prefix used in the message
        message_content = ctx.message.content
        prefix_used = None
        for prefix in self.prefixes:
            if message_content.startswith(prefix):
                prefix_used = prefix
                break

        if not prefix_used:
            # Default prefix if not found, adjust as necessary
            prefix_used = '#'

        # Extract the command used by parsing the message content
        try:
            command_with_prefix = message_content.split()[0]  # e.g., "#gn"
            command_used = command_with_prefix[len(prefix_used):].lower()  # e.g., "gn"
        except IndexError:
            # If the message is just the prefix without a command
            await ctx.send(f"@{username}, please provide a reason for going AFK.")
            return

        base_reason = {
            "afk": "AFK",
            "sleep": "sleeping",
            "gn": "sleeping",
            "bed": "sleeping",
            "work": "working",
            "food": "eating",
            "gaming": "gaming"
        }.get(command_used, "AFK")  # Default to "AFK" if alias not found

        # Construct the full reason with user-provided details if any
        if reason:
            full_reason = f"{base_reason}: {reason}"
        else:
            full_reason = base_reason

        afk_time = time.time()

        # Insert or update the AFK status in the database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO afk (user_id, username, afk_time, reason, return_time, active)
            VALUES (?, ?, ?, ?, NULL, 1)
        ''', (user_id, username, afk_time, full_reason))
        conn.commit()
        conn.close()

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
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT afk_time, reason, return_time, active FROM afk WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()

        if row:
            afk_time, full_reason, return_time, active_status = row
            if active_status == 0 and return_time is not None:
                time_since_return = time.time() - return_time
                if time_since_return <= 5 * 60:  # 5 minutes
                    # Resume AFK
                    cursor.execute('''
                        UPDATE afk
                        SET active = 1, return_time = NULL
                        WHERE user_id = ?
                    ''', (user_id,))
                    conn.commit()
                    conn.close()
                    await ctx.send(f"@{username} has resumed {full_reason}")
                else:
                    conn.close()
                    await ctx.send(f"@{username}, it's been more than 5 minutes since you returned. Cannot resume AFK.")
            else:
                conn.close()
                await ctx.send(f"@{username}, you are not eligible to resume AFK.")
        else:
            conn.close()
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
        if hasattr(self.bot, 'bot_user_id') and message.author.id == self.bot.bot_user_id:
            return

        # Prevent responding to AFK commands themselves
        if self.is_afk_command(message):
            return

        # Check if the user is currently AFK
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT afk_time, reason, return_time, active FROM afk WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            afk_time, full_reason, return_time, active_status = row

            if active_status == 1:
                # User is currently AFK and active
                afk_duration = time.time() - afk_time
                days, hours, minutes, seconds = self.format_duration(afk_duration)

                # Parse the full_reason into base_reason and user_reason
                if ': ' in full_reason:
                    base_reason, user_reason = full_reason.split(': ', 1)
                else:
                    base_reason = full_reason
                    user_reason = None

                # Format the "no longer AFK" message based on whether a reason was provided
                if user_reason:
                    no_longer_afk_message = f"@{username} is no longer {base_reason}: {user_reason} ({int(seconds)}s ago)"
                else:
                    no_longer_afk_message = f"@{username} is no longer {base_reason}. ({int(seconds)}s ago)"

                # Check if a "no longer AFK" message was recently sent to prevent spamming
                if user_id in self.last_afk_message_time:
                    time_since_last_message = time.time() - self.last_afk_message_time[user_id]
                    if time_since_last_message < 3:
                        return

                # Send the "no longer AFK" message
                await message.channel.send(no_longer_afk_message)
                self.last_afk_message_time[user_id] = time.time()

                # Update the user's AFK status to inactive and set return_time
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE afk
                    SET active = 0, return_time = ?
                    WHERE user_id = ?
                ''', (time.time(), user_id))
                conn.commit()
                conn.close()
            else:
                # User was AFK but is now inactive
                if return_time is not None:
                    time_since_return = time.time() - return_time
                    if time_since_return > 5 * 60:  # 5 minutes
                        # Remove the AFK entry
                        conn = sqlite3.connect(self.db_path)
                        cursor = cursor = conn.cursor()
                        cursor.execute('DELETE FROM afk WHERE user_id = ?', (user_id,))
                        conn.commit()
                        conn.close()

    def is_afk_command(self, message):
        message_content = message.content.strip()
        # Get prefixes
        prefixes = self.prefixes
        # Check if message starts with any prefix
        for prefix in prefixes:
            if message_content.startswith(prefix):
                # Extract command
                command_with_prefix = message_content.split()[0]  # e.g., "#afk"
                command_used = command_with_prefix[len(prefix):].lower()
                if command_used in ['afk', 'sleep', 'gn', 'work', 'food', 'gaming', 'bed', 'rafk']:
                    return True
        return False

    def format_duration(self, duration):
        """
        Takes a duration in seconds and returns (days, hours, minutes, seconds)
        """
        days = int(duration // (24 * 3600))
        duration %= (24 * 3600)
        hours = int(duration // 3600)
        duration %= 3600
        minutes = int(duration // 60)
        seconds = duration % 60
        return days, hours, minutes, seconds

    def log_missing_data(self, message):
        # Implement logging for missing data if necessary
        self.bot.logger.warning(
            f"Received a message with missing data. Content: {getattr(message, 'content', 'None')}, "
            f"Channel: {getattr(message.channel, 'name', 'None')}"
        )

def prepare(bot):
    bot.add_cog(Afk(bot))