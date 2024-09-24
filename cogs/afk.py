import sqlite3
from twitchio.ext import commands
import time
from watch import Watch  # Ensure this import is correct and Watch is properly defined

class Afk(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_path = 'afk.db'
        self._setup_database()
        self.last_afk_command_time = {}
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
                reason TEXT
            )
        ''')
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
            INSERT OR REPLACE INTO afk (user_id, username, afk_time, reason)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, afk_time, full_reason))
        conn.commit()
        conn.close()

        # Update the last AFK command time to prevent immediate response upon setting AFK
        self.last_afk_command_time[user_id] = time.time()
        await ctx.send(f"@{username} is now {full_reason}.")

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

        # Prevent responding to AFK command itself
        if user_id in self.last_afk_command_time:
            time_since_last_afk_command = time.time() - self.last_afk_command_time[user_id]
            if time_since_last_afk_command < 3:
                return

        # Check if the user is currently AFK
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT afk_time, reason FROM afk WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            afk_time = row[0]
            full_reason = row[1]
            afk_duration = Watch.get_afk_duration(afk_time)
            weeks, days, hours, minutes, seconds = Watch.format_duration(afk_duration)

            # Parse the full_reason into base_reason and user_reason
            if ': ' in full_reason:
                base_reason, user_reason = full_reason.split(': ', 1)
            else:
                base_reason = full_reason
                user_reason = None

            # Format the "no longer AFK" message based on whether a reason was provided
            if user_reason:
                no_longer_afk_message = f"@{username} is no longer {base_reason}: {user_reason} ({seconds:.2f}s ago)"
            else:
                no_longer_afk_message = f"@{username} is no longer {base_reason}. ({seconds:.2f}s ago)"

            # Check if a "no longer AFK" message was recently sent to prevent spamming
            if user_id in self.last_afk_message_time:
                time_since_last_message = time.time() - self.last_afk_message_time[user_id]
                if time_since_last_message < 3:
                    return

            # Send the "no longer AFK" message
            await message.channel.send(no_longer_afk_message)
            self.last_afk_message_time[user_id] = time.time()

            # Remove the user's AFK status from the database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM afk WHERE user_id = ?', (user_id,))
            conn.commit()
            conn.close()

    def log_missing_data(self, message):
        # Implement logging for missing data if necessary
        self.bot.logger.warning(
            f"Received a message with missing data. Content: {getattr(message, 'content', 'None')}, "
            f"Channel: {getattr(message.channel, 'name', 'None')}"
        )

def setup(bot: commands.Bot):
    bot.add_cog(Afk(bot))
