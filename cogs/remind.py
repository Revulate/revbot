import asyncio
import uuid
from datetime import datetime, timezone, timedelta
import aiosqlite
from twitchio.ext import commands
from utils import parse_time, format_time_delta, normalize_username, fetch_user, get_channel, setup_database


class Reminder:
    def __init__(
        self,
        reminder_id,
        user,
        target,
        message,
        channel_id,
        channel_name,
        remind_time=None,
        private=False,
        trigger_on_message=False,
        created_at=None,
    ):
        self.id = reminder_id
        self.user = user
        self.target = target
        self.message = message
        self.channel_id = channel_id
        self.channel_name = channel_name
        self.remind_time = remind_time
        self.private = private
        self.trigger_on_message = trigger_on_message
        self.active = True
        self.created_at = created_at


class Remind(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "bot.db"
        self.last_channel_per_user = {}
        self.check_timed_reminders_task = None

    async def setup_database(self):
        await setup_database(self.db_path)

    async def close_database(self):
        # Placeholder for closing any persistent connections if needed.
        pass

    @commands.Cog.event()
    async def event_ready(self):
        await self.setup_database()
        self.check_timed_reminders_task = self.bot.loop.create_task(self.check_timed_reminders())

    async def check_timed_reminders(self):
        while True:
            try:
                now = datetime.now(timezone.utc)
                async with aiosqlite.connect(self.db_path) as conn:
                    async with conn.execute(
                        "SELECT * FROM reminders WHERE remind_time IS NOT NULL AND active=1"
                    ) as cursor:
                        rows = await cursor.fetchall()

                for row in rows:
                    reminder = self.row_to_reminder(row)
                    if now >= reminder.remind_time:
                        channel = get_channel(self.bot, reminder.channel_name)
                        if channel:
                            await self.send_reminder(reminder, channel)
                            await self.remove_reminder(reminder.id)

                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.bot.logger.error(f"Error in check_timed_reminders: {e}")
                await asyncio.sleep(5)

    @commands.Cog.event()
    async def event_message(self, message):
        if message.echo or not message.channel:
            return

        if hasattr(self.bot, "bot_user_id") and message.author.id == self.bot.bot_user_id:
            return

        user_id = message.author.id
        channel = message.channel

        message_time = message.timestamp or datetime.now(timezone.utc)
        if message_time.tzinfo is None:
            message_time = message_time.replace(tzinfo=timezone.utc)

        self.last_channel_per_user[user_id] = channel

        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute(
                "SELECT * FROM reminders WHERE target_id = ? AND trigger_on_message = 1 AND active = 1", (user_id,)
            ) as cursor:
                rows = await cursor.fetchall()

        for row in rows:
            reminder = self.row_to_reminder(row)
            if message_time >= reminder.created_at:
                await self.send_reminder(reminder, channel)
                await self.remove_reminder(reminder.id)

    @commands.command(name="remind")
    async def remind_command(self, ctx: commands.Context, target_identifier: str, *, message: str):
        target_identifier = normalize_username(target_identifier)
        target = await fetch_user(self.bot, target_identifier)
        if not target:
            await ctx.send(f"@{ctx.author.name}, user '{target_identifier}' not found.")
            return

        reminder_id = str(uuid.uuid4())[:8]
        channel_name = ctx.channel.name
        channel_id = ctx.channel.name  # Use channel name as ID
        created_at = ctx.message.timestamp or datetime.now(timezone.utc)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        remind_time_delta, message = parse_time(message.split())
        if remind_time_delta and isinstance(remind_time_delta, timedelta):
            remind_time = created_at + remind_time_delta
        else:
            remind_time = None

        reminder = Reminder(
            reminder_id=reminder_id,
            user=ctx.author,
            target=target,
            message=message,
            channel_id=channel_id,
            channel_name=channel_name,
            remind_time=remind_time,
            created_at=created_at,
            trigger_on_message=True,
        )

        await self.save_reminder(reminder)
        await ctx.send(f"@{ctx.author.name}, reminder set for @{target.name}: {message} - ID: {reminder.id}")

    async def save_reminder(self, reminder: Reminder):
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """
                INSERT INTO reminders (id, user_id, username, target_id, target_name, channel_id, channel_name,
                message, remind_time, private, trigger_on_message, active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reminder.id,
                    reminder.user.id,
                    reminder.user.name,
                    reminder.target.id,
                    reminder.target.name,
                    reminder.channel_id,
                    reminder.channel_name,
                    reminder.message,
                    reminder.remind_time.isoformat() if reminder.remind_time else None,
                    int(reminder.private),
                    int(reminder.trigger_on_message),
                    int(reminder.active),
                    reminder.created_at.isoformat(),
                ),
            )
            await conn.commit()

    async def send_reminder(self, reminder: Reminder, channel):
        remind_time = reminder.remind_time or reminder.created_at
        time_since_set = format_time_delta(datetime.now(timezone.utc) - remind_time)
        message = f"@{reminder.target.name}, reminder from @{reminder.user.name} set {time_since_set} ago - {reminder.message}"

        if reminder.private:
            try:
                await reminder.target.send(message)
            except Exception as e:
                self.bot.logger.error(f"Failed to send private reminder: {e}")
        else:
            try:
                await channel.send(message)
            except Exception as e:
                self.bot.logger.error(f"Failed to send reminder: {e}")

    async def remove_reminder(self, reminder_id: str):
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
            await conn.commit()

    def row_to_reminder(self, row):
        return Reminder(
            reminder_id=row[0],
            user=self.bot.create_user(row[1], row[2]),
            target=self.bot.create_user(row[3], row[4]),
            message=row[7],
            channel_id=row[5],
            channel_name=row[6],
            remind_time=datetime.fromisoformat(row[8]) if row[8] else None,
            private=bool(row[9]),
            trigger_on_message=bool(row[10]),
            created_at=datetime.fromisoformat(row[12]),
        )


def prepare(bot):
    bot.add_cog(Remind(bot))
