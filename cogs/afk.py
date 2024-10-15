import time
import aiosqlite
from twitchio.ext import commands
import re


class Afk(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "bot.db"
        self.last_afk_message_time = {}

    async def setup_database(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
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
            await db.commit()

    @commands.command(name="afk", aliases=["sleep", "gn", "work", "food", "gaming", "bed"])
    async def afk_command(self, ctx: commands.Context, *, reason: str = None):
        user_id = ctx.author.id
        username = ctx.author.name
        command_used = ctx.message.content.split()[0][1:].lower()
        base_reason = {
            "afk": "AFK",
            "sleep": "sleeping",
            "gn": "sleeping",
            "bed": "sleeping",
            "work": "working",
            "food": "eating",
            "gaming": "gaming",
        }.get(command_used, "AFK")
        full_reason = f"{base_reason}: {reason}" if reason else base_reason
        afk_time = time.time()

        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO afk (user_id, username, afk_time, reason, return_time, active)
                VALUES (?, ?, ?, ?, NULL, 1)
            """,
                (user_id, username, afk_time, full_reason),
            )
            await conn.commit()

        await ctx.send(f"@{username} is now {full_reason}")

    @commands.command(name="rafk")
    async def rafk_command(self, ctx: commands.Context):
        user_id = ctx.author.id
        username = ctx.author.name

        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute(
                "SELECT afk_time, reason, return_time, active FROM afk WHERE user_id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()

            if row:
                afk_time, full_reason, return_time, active_status = row
                if active_status == 0 and return_time is not None:
                    time_since_return = time.time() - return_time
                    if time_since_return <= 5 * 60:  # 5 minutes
                        await conn.execute(
                            """
                            UPDATE afk
                            SET active = 1, return_time = NULL
                            WHERE user_id = ?
                        """,
                            (user_id,),
                        )
                        await conn.commit()
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
        if message.echo or not message.channel or not message.author:
            return

        if hasattr(self.bot, "bot_user_id") and message.author.id == self.bot.bot_user_id:
            return

        if self.is_afk_command(message):
            return

        await self._handle_afk_return(message, message.author.id, message.author.name)

    async def _handle_afk_return(self, message, user_id, username):
        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute(
                "SELECT afk_time, reason, return_time, active FROM afk WHERE user_id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()

            if row:
                afk_time, full_reason, return_time, active_status = row

                if active_status == 1:
                    await self._send_afk_return_message(message, user_id, username, afk_time, full_reason)
                    await conn.execute(
                        """
                        UPDATE afk
                        SET active = 0, return_time = ?
                        WHERE user_id = ?
                    """,
                        (time.time(), user_id),
                    )
                    await conn.commit()

    async def _send_afk_return_message(self, message, user_id, username, afk_time, full_reason):
        afk_duration = time.time() - afk_time
        time_string = self.format_duration_string(afk_duration)
        base_reason, user_reason = full_reason.split(": ", 1) if ": " in full_reason else (full_reason, None)
        no_longer_afk_message = (
            f"@{username} is no longer {base_reason}: {user_reason} ({time_string} ago)"
            if user_reason
            else f"@{username} is no longer {base_reason}. ({time_string} ago)"
        )

        if user_id in self.last_afk_message_time:
            time_since_last_message = time.time() - self.last_afk_message_time[user_id]
            if time_since_last_message < 3:  # 3 seconds cooldown
                return

        await message.channel.send(no_longer_afk_message)
        self.last_afk_message_time[user_id] = time.time()

    def is_afk_command(self, message):
        return message.content.strip().lower().split()[0] in [
            f"#{cmd}" for cmd in ["afk", "sleep", "gn", "work", "food", "gaming", "bed", "rafk"]
        ]

    def format_duration_string(self, duration):
        days, remainder = divmod(int(duration), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if seconds > 0 or not parts:
            parts.append(f"{seconds}s")
        return " ".join(parts)


def prepare(bot):
    bot.add_cog(Afk(bot))
