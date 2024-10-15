import aiosqlite
from twitchio.ext import commands
from datetime import datetime, timezone


class MessageLogger(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "chat_logs.db"
        self.bot.loop.create_task(self.setup_database())

    async def setup_database(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    channel TEXT,
                    user_id TEXT,
                    username TEXT,
                    display_name TEXT,
                    message TEXT,
                    timestamp TEXT,
                    tags TEXT
                )
            """
            )
            await db.execute("CREATE INDEX IF NOT EXISTS idx_channel_timestamp ON messages(channel, timestamp)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_username ON messages(username)")
            await db.commit()

    @commands.Cog.event()
    async def event_message(self, message):
        if message.echo:
            return
        await self.log_message(message)

    async def log_message(self, message):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO messages 
                (id, channel, user_id, username, display_name, message, timestamp, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    message.id,
                    message.channel.name,
                    str(message.author.id),
                    message.author.name,
                    message.author.display_name,
                    message.content,
                    message.timestamp.replace(tzinfo=timezone.utc).isoformat(),
                    str(message.tags),
                ),
            )
            await db.commit()

    async def get_last_message(self, channel: str, username: str):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT message, timestamp FROM messages WHERE channel = ? AND username = ? ORDER BY timestamp DESC LIMIT 1",
                (channel, username),
            ) as cursor:
                return await cursor.fetchone()


def prepare(bot):
    bot.add_cog(MessageLogger(bot))
