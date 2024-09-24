import sqlite3
from twitchio.ext import commands
import time
from watch import Watch  # Import the Watch class

class Afk(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_path = 'afk.db'
        self._setup_database()
        self.last_afk_command_time = {}
        self.last_afk_message_time = {}

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

    def format_afk_message(self, username, reason, weeks, days, hours, minutes, seconds):
        if reason.lower().startswith("sleeping"):
            afk_text = "is now sleeping"
        elif reason.lower().startswith("working"):
            afk_text = "is now working"
        elif reason.lower().startswith("gaming"):
            afk_text = "is now gaming"
        elif reason.lower().startswith("eating"):
            afk_text = "is now eating"
        else:
            afk_text = "is now AFK"

        if weeks > 0:
            return f"@{username} {afk_text} ({int(weeks)}w, {int(days)}d ago)"
        elif days > 0:
            return f"@{username} {afk_text} ({int(days)}d, {int(hours)}h ago)"
        elif hours > 0:
            return f"@{username} {afk_text} ({int(hours)}h, {int(minutes)}m ago)"
        elif minutes > 0:
            return f"@{username} {afk_text} ({int(minutes)}m, {int(seconds)}s ago)"
        else:
            return f"@{username} {afk_text} ({int(seconds)}s ago)"

    @commands.command(name="afk", aliases=["sleep", "gn", "work", "food", "gaming", "bed"])
    async def afk_command(self, ctx: commands.Context, *, reason: str = None):
        user_id = ctx.author.id
        username = ctx.author.name

        alias = ctx.command.name.lower()
        base_reason = {
            "sleep": "sleeping",
            "gn": "sleeping",
            "bed": "sleeping",
            "work": "working",
            "food": "eating",
            "gaming": "gaming"
        }.get(alias, "afk")

        full_reason = f"{base_reason}: {reason}" if reason else base_reason
        afk_time = time.time()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO afk (user_id, username, afk_time, reason)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, afk_time, full_reason))
        conn.commit()
        conn.close()

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

        if user_id in self.last_afk_command_time:
            time_since_last_afk_command = time.time() - self.last_afk_command_time[user_id]
            if time_since_last_afk_command < 3:
                return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT afk_time, reason FROM afk WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            afk_time = row[0]
            reason = row[1]
            afk_duration = Watch.get_afk_duration(afk_time)
            weeks, days, hours, minutes, seconds = Watch.format_duration(afk_duration)

            afk_message = self.format_afk_message(username, reason, weeks, days, hours, minutes, seconds)

            if user_id in self.last_afk_message_time:
                time_since_last_message = time.time() - self.last_afk_message_time[user_id]
                if time_since_last_message < 3:
                    return

            # Correct the message sent when returning from AFK
            await message.channel.send(f"@{username} is no longer AFK ({int(seconds)}s ago)")
            self.last_afk_message_time[user_id] = time.time()

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM afk WHERE user_id = ?', (user_id,))
            conn.commit()
            conn.close()

def setup(bot: commands.Bot):
    bot.add_cog(Afk(bot))
