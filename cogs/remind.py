# cogs/remind.py

import logging
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
import re
import aiosqlite

from twitchio.ext import commands

from utils import fetch_user, get_channel, parse_time, format_time_delta, setup_database

logger = logging.getLogger("twitch_bot.cogs.remind")


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
        self.logger = logger
        self.db_path = "reminders.db"
        self.last_channel_per_user = {}
        setup_database(self.db_path)
        self.check_timed_reminders_task = None
        self.prefixes = self._get_prefixes()

    def _get_prefixes(self):
        prefix = getattr(self.bot, "prefix", getattr(self.bot, "_prefix", "#"))
        return prefix if isinstance(prefix, list) else [prefix]

    def cog_load(self):
        if not self.check_timed_reminders_task or self.check_timed_reminders_task.done():
            self.check_timed_reminders_task = self.bot.loop.create_task(self.check_timed_reminders())

    def cog_unload(self):
        if self.check_timed_reminders_task:
            self.check_timed_reminders_task.cancel()
            try:
                self.bot.loop.run_until_complete(self.check_timed_reminders_task)
            except asyncio.CancelledError:
                pass
            self.check_timed_reminders_task = None

    async def check_timed_reminders(self):
        try:
            while True:
                now = datetime.now(timezone.utc)
                reminders_to_send = []

                async with aiosqlite.connect(self.db_path) as conn:
                    async with conn.execute(
                        "SELECT * FROM reminders WHERE remind_time IS NOT NULL AND active=1"
                    ) as cursor:
                        rows = await cursor.fetchall()

                for row in rows:
                    if len(row) != 13:
                        self.logger.error(f"Unexpected number of columns in row: {row}")
                        continue
                    (
                        reminder_id,
                        user_id,
                        username,
                        target_id,
                        target_name,
                        channel_id,
                        channel_name,
                        message,
                        remind_time_str,
                        private,
                        trigger_on_message,
                        active,
                        created_at_str,
                    ) = row
                    try:
                        remind_time = datetime.fromisoformat(remind_time_str)
                        if remind_time.tzinfo is None:
                            remind_time = remind_time.replace(tzinfo=timezone.utc)
                    except (TypeError, ValueError) as e:
                        self.logger.error(
                            f"Invalid datetime format for reminder {reminder_id}: {remind_time_str} Error: {e}"
                        )
                        await self.remove_reminder(reminder_id)
                        continue

                    if now >= remind_time:
                        user = await fetch_user(self.bot, str(user_id))
                        if not user:
                            self.logger.warning(f"User '{username}' with ID '{user_id}' not found.")
                            continue

                        target = await fetch_user(self.bot, str(target_id))
                        if not target:
                            self.logger.warning(f"Target user '{target_name}' with ID '{target_id}' not found.")
                            continue

                        channel = get_channel(self.bot, channel_name)
                        if not channel:
                            self.logger.warning(f"Channel '{channel_name}' not found in bot's connected channels.")
                            continue

                        reminders_to_send.append(
                            (
                                channel,
                                Reminder(
                                    reminder_id,
                                    user,
                                    target,
                                    message,
                                    channel_id,
                                    channel_name,
                                    remind_time=remind_time,
                                    private=bool(private),
                                    trigger_on_message=bool(trigger_on_message),
                                    created_at=datetime.fromisoformat(created_at_str) if created_at_str else None,
                                ),
                            )
                        )

                for channel, reminder in reminders_to_send:
                    self.logger.debug(
                        f"Sending reminder ID {reminder.id} to user {reminder.target.name} in channel {reminder.channel_name}."
                    )
                    try:
                        await self.send_reminder(reminder, channel)
                    except Exception as e:
                        self.logger.error(
                            f"Failed to send reminder ID {reminder.id} to user {reminder.target.name} in channel {reminder.channel_name}: {e}"
                        )
                    await self.remove_reminder(reminder.id)

                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            self.logger.info("check_timed_reminders task has been cancelled.")

    async def send_reminder(self, reminder: Reminder, channel):
        remind_time = reminder.remind_time or reminder.created_at
        time_since_set = format_time_delta(datetime.now(timezone.utc) - remind_time) if remind_time else "unknown"
        if reminder.user:
            message = f"@{reminder.target.name}, reminder from @{reminder.user.name} set {time_since_set} ago - {reminder.message}"
        else:
            message = f"@{reminder.target.name}, reminder set {time_since_set} ago - {reminder.message}"
        if reminder.private:
            try:
                await reminder.target.send(message)
                self.logger.debug(f"Sent private reminder to {reminder.target.name}: {message}")
            except Exception as e:
                self.logger.error(f"Failed to send private reminder to {reminder.target.name}: {e}")
        else:
            try:
                await channel.send(message)
                self.logger.debug(f"Sent reminder to {reminder.target.name} in {channel.name}: {message}")
            except Exception as e:
                self.logger.error(f"Failed to send reminder to {reminder.target.name} in {channel.name}: {e}")

    @commands.Cog.event()
    async def event_message(self, message):
        if message.echo or not message.channel:
            return

        if hasattr(self.bot, "bot_user_id") and message.author.id == self.bot.bot_user_id:
            return

        if not message.author:
            self.log_missing_data(message)
            return

        if self.is_command(message):
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
        self.logger.debug(f"Fetched {len(rows)} trigger_on_message reminders for user {user_id}.")

        for row in rows:
            if len(row) != 13:
                self.logger.error(f"Unexpected number of columns in row: {row}")
                continue
            (
                reminder_id,
                user_id_db,
                username,
                target_id,
                target_name,
                channel_id,
                channel_name,
                message_text,
                remind_time_str,
                private,
                trigger_on_message,
                active,
                created_at_str,
            ) = row

            try:
                created_at = datetime.fromisoformat(created_at_str)
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError) as e:
                self.logger.error(
                    f"Invalid 'created_at' format for reminder {reminder_id}: {created_at_str} Error: {e}"
                )
                await self.remove_reminder(reminder_id)
                continue

            if message_time < created_at:
                continue

            user = await fetch_user(self.bot, str(user_id_db))
            if not user:
                self.logger.warning(f"User '{username}' with ID '{user_id_db}' not found.")
                continue

            reminder = Reminder(
                reminder_id,
                user,
                message.author,
                message_text,
                channel_id,
                channel_name,
                remind_time=None,
                private=bool(private),
                trigger_on_message=bool(trigger_on_message),
                created_at=created_at,
            )
            try:
                await self.send_reminder(reminder, channel)
            except Exception as e:
                self.logger.error(
                    f"Failed to send reminder ID {reminder.id} to user {reminder.target.name} in channel {reminder.channel_name}: {e}"
                )
            await self.remove_reminder(reminder.id)

    @commands.command(name="remind")
    async def remind_command(self, ctx: commands.Context, target_identifier: str, *, message: str):
        target = await fetch_user(self.bot, target_identifier)
        if not target:
            await ctx.send(f"@{ctx.author.name}, user '{target_identifier}' not found.")
            return

        reminder_id = str(uuid.uuid4())[:8]
        channel_name = ctx.channel.name
        channel_id = ctx.channel.name
        created_at = ctx.message.timestamp or datetime.now(timezone.utc)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        # Parse reminder time from message
        remind_time_delta, message = parse_time(message)
        remind_time = created_at + remind_time_delta if remind_time_delta else None

        reminder = Reminder(
            reminder_id=reminder_id,
            user=ctx.author,
            target=target,
            message=message,
            channel_id=channel_id,
            channel_name=channel_name,
            remind_time=remind_time,
            created_at=created_at,
            trigger_on_message=True,  # Ensure trigger_on_message is set to True for the command to work
        )

        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """INSERT INTO reminders (id, user_id, username, target_id, target_name, channel_id, channel_name,
                message, remind_time, private, trigger_on_message, active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    reminder.id,
                    reminder.user.id,
                    reminder.user.name,
                    reminder.target.id,
                    reminder.target.name,
                    reminder.channel_id,
                    reminder.channel_name,
                    reminder.message,
                    remind_time.isoformat() if remind_time else None,
                    int(reminder.private),
                    int(reminder.trigger_on_message),
                    int(reminder.active),
                    reminder.created_at.isoformat(),
                ),
            )
            await conn.commit()

        await ctx.send(f"@{ctx.author.name}, reminder set for @{target.name}: {message} - ID: {reminder.id}")

    def is_command(self, message):
        message_content = message.content.strip()
        pattern = f"^({'|'.join(re.escape(prefix) for prefix in self.prefixes)})(\w+)"
        match = re.match(pattern, message_content)
        return bool(match)

    def log_missing_data(self, message):
        self.logger.warning(
            f"Received a message with missing data. Content: {getattr(message, 'content', 'None')}, "
            f"Channel: {getattr(message.channel, 'name', 'None')}"
        )

    async def remove_reminder(self, reminder_id: str):
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
            await conn.commit()


def prepare(bot):
    bot.add_cog(Remind(bot))
