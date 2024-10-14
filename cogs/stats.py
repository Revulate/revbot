import time
from twitchio.ext import commands
from datetime import datetime, timezone
import aiosqlite


class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "user_stats.db"
        self.bot.loop.create_task(self.setup_database())

    async def setup_database(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
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
            await db.commit()

    @commands.Cog.event()
    async def event_message(self, message):
        if message.echo:
            return

        user_id = message.author.id
        username = message.author.name
        current_time = datetime.now(timezone.utc)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO user_stats (user_id, username, message_count, first_seen, last_seen)
                VALUES (?, ?, 1, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    message_count = message_count + 1,
                    last_seen = ?
            """,
                (user_id, username, current_time, current_time, current_time),
            )
            await db.commit()

    @commands.command(name="stats")
    async def stats_command(self, ctx: commands.Context, username: str = None):
        if username is None:
            username = ctx.author.name

        user = await self.bot.fetch_users([username])
        if not user:
            await ctx.send(f"@{ctx.author.name}, user '{username}' not found.")
            return

        user = user[0]
        user_id = str(user.id)

        # Fetch user stats from Twitch API
        try:
            channel_info = await self.bot.fetch_channels([user_id])
            channel_info = channel_info[0] if channel_info else None
        except Exception as e:
            self.bot.logger.error(f"Error fetching channel info: {e}")
            channel_info = None

        # Fetch user stats from our database
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT message_count, first_seen, last_seen FROM user_stats WHERE user_id = ?", (user_id,)
            ) as cursor:
                db_stats = await cursor.fetchone()

        # Prepare stats message
        stats = []
        stats.append(f"Stats for {user.display_name} (ID: {user.id}):")
        stats.append(f"Account created: {self.format_time_ago(user.created_at)}")

        if channel_info and channel_info.game_name:
            stats.append(f"Current game: {channel_info.game_name}")

        if channel_info and hasattr(channel_info, "language"):
            stats.append(f"Language: {channel_info.language}")

        if db_stats:
            message_count, first_seen, last_seen = db_stats
            stats.append(f"Messages sent in this channel: {message_count}")
            stats.append(f"First seen in this channel: {self.format_time_ago(first_seen)}")
            stats.append(f"Last seen in this channel: {self.format_time_ago(last_seen)}")
        else:
            stats.append("No message history found in this channel.")

        # Fetch follow information
        try:
            follows = await self.bot.fetch_followers(user_id, first=1)
            if follows:
                stats.append(f"Followers: {follows.total}")
        except Exception as e:
            self.bot.logger.error(f"Error fetching follower count: {e}")

        # Send stats
        await ctx.send(" | ".join(stats))

    def format_time_ago(self, timestamp):
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.rstrip("Z")).replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        delta = now - timestamp

        if delta.days > 365:
            years = delta.days // 365
            return f"{years} year{'s' if years != 1 else ''} ago"
        elif delta.days > 30:
            months = delta.days // 30
            return f"{months} month{'s' if months != 1 else ''} ago"
        elif delta.days > 0:
            return f"{delta.days} day{'s' if delta.days != 1 else ''} ago"
        elif delta.seconds > 3600:
            hours = delta.seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif delta.seconds > 60:
            minutes = delta.seconds // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        else:
            return f"{delta.seconds} second{'s' if delta.seconds != 1 else ''} ago"


def prepare(bot):
    bot.add_cog(Stats(bot))
