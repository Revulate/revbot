# cogs/remind.py
import logging
import asyncio
import uuid
from datetime import datetime, timezone

from twitchio.ext import commands

from utils import (fetch_user, get_channel, parse_time, format_time_delta,
                   setup_database, remove_reminder, get_database_connection)

logger = logging.getLogger('twitch_bot.cogs.remind')


class Reminder:
    """A class representing a reminder."""

    def __init__(self, reminder_id, user, target, message, channel_id, channel_name,
                 remind_time=None, private=False, trigger_on_message=False):
        self.id = reminder_id
        self.user = user  # User who set the reminder (User object)
        self.target = target  # User to be reminded (User object)
        self.message = message
        self.channel_id = channel_id  # User ID of the channel owner
        self.channel_name = channel_name
        self.remind_time = remind_time  # datetime object or None
        self.private = private
        self.trigger_on_message = trigger_on_message
        self.active = True


class Remind(commands.Cog):
    """Cog for handling reminders."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logger
        self.db_path = 'reminders.db'
        self.last_channel_per_user = {}
        setup_database(self.db_path)
        self.bot.loop.create_task(self.check_timed_reminders())

    async def check_timed_reminders(self):
        """Background task to check and send timed reminders."""
        try:
            while True:
                now = datetime.now(timezone.utc)
                reminders_to_send = []

                conn = get_database_connection(self.db_path)
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM reminders WHERE remind_time IS NOT NULL AND active=1')
                rows = cursor.fetchall()
                conn.close()

                for row in rows:
                    if len(row) != 12:
                        self.logger.error(f"Unexpected number of columns in row: {row}")
                        continue
                    reminder_id, user_id, username, target_id, target_name, channel_id, channel_name, message, remind_time_str, private, trigger_on_message, active = row
                    try:
                        remind_time = datetime.fromisoformat(remind_time_str)
                        if remind_time.tzinfo is None:
                            remind_time = remind_time.replace(tzinfo=timezone.utc)
                    except (TypeError, ValueError) as e:
                        self.logger.error(f"Invalid datetime format for reminder {reminder_id}: {remind_time_str} Error: {e}")
                        remove_reminder(reminder_id, self.db_path)
                        continue

                    if now >= remind_time:
                        # Fetch user who set the reminder
                        user = await fetch_user(self.bot, user_id)
                        if not user:
                            self.logger.warning(f"User '{username}' with ID '{user_id}' not found.")
                            user = type('User', (object,), {'name': username, 'id': user_id})

                        # Fetch target user
                        target = await fetch_user(self.bot, target_id)
                        if not target:
                            self.logger.warning(f"Target user '{target_name}' with ID '{target_id}' not found.")
                            target = type('User', (object,), {'name': target_name, 'id': target_id})

                        # Get the channel
                        channel = get_channel(self.bot, channel_name)
                        if not channel:
                            self.logger.warning(f"Channel '{channel_name}' not found in bot's connected channels.")
                            continue

                        reminders_to_send.append((channel, Reminder(
                            reminder_id, user, target, message,
                            channel_id, channel_name, remind_time=remind_time,
                            private=bool(private), trigger_on_message=bool(trigger_on_message)
                        )))

                for channel, reminder in reminders_to_send:
                    await self.send_reminder(reminder, channel)
                    remove_reminder(reminder.id, self.db_path)

                await asyncio.sleep(1)  # Check every second
        except asyncio.CancelledError:
            self.logger.info("check_timed_reminders task has been cancelled.")

    async def send_reminder(self, reminder: Reminder, channel):
        """Sends the reminder message to the target user in the specified channel."""
        if reminder.user:
            message = f"@{reminder.target.name}, reminder from @{reminder.user.name} - {reminder.message}"
        else:
            message = f"@{reminder.target.name}, reminder - {reminder.message}"
        if reminder.private:
            try:
                await reminder.target.send(message)  # Sending a whisper/PM
                self.logger.debug(f"Sent private reminder to {reminder.target.name}: {message}")
            except Exception as e:
                self.logger.error(f"Failed to send private reminder to {reminder.target.name}: {e}")
        else:
            await channel.send(message)
            self.logger.debug(f"Sent reminder to {reminder.target.name} in {channel.name}: {message}")

    @commands.Cog.event()
    async def event_message(self, message):
        """Event handler to trigger reminders when a user sends a message."""
        if message.echo:
            return  # Ignore messages sent by the bot itself

        if not message.author:
            self.log_missing_data(message)
            return

        user_id = message.author.id
        channel = message.channel

        # Update the last channel the user sent a message in
        self.last_channel_per_user[user_id] = channel

        # Check if the user has any active trigger_on_message reminders
        conn = get_database_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM reminders WHERE target_id = ? AND trigger_on_message = 1 AND active = 1', (user_id,))
        rows = cursor.fetchall()
        conn.close()

        for row in rows:
            if len(row) != 12:
                self.logger.error(f"Unexpected number of columns in row: {row}")
                continue
            reminder_id, user_id_db, username, target_id, target_name, channel_id, channel_name, message_text, remind_time_str, private, trigger_on_message, active = row

            # Fetch user who set the reminder
            user = await fetch_user(self.bot, user_id_db)
            if not user:
                self.logger.warning(f"User '{username}' with ID '{user_id_db}' not found.")
                user = type('User', (object,), {'name': username, 'id': user_id_db})

            reminder = Reminder(
                reminder_id, user, message.author, message_text,
                channel_id, channel_name,
                remind_time=None, private=bool(private), trigger_on_message=bool(trigger_on_message)
            )
            await self.send_reminder(reminder, channel)
            remove_reminder(reminder.id, self.db_path)

    @commands.command(name='remind')
    async def remind(self, ctx: commands.Context, target_identifier: str = None, *args):
        """
        Sets a reminder for another user.

        Usage:
        - #remind (person) [in/on/after time] message
        """
        self.logger.info(f"Processing command 'remind' from {ctx.author.name}: Target={target_identifier}, Args={args}")

        if not target_identifier:
            await ctx.send(f"@{ctx.author.name}, please provide a target for the reminder.")
            return

        # Fetch the target user
        target = await fetch_user(self.bot, target_identifier)
        if not target:
            await ctx.send(f"@{ctx.author.name}, user '{target_identifier}' not found.")
            return

        if not args:
            await ctx.send(f"@{ctx.author.name}, please provide a message for the reminder.")
            return

        # Parse time and message
        remind_time, message_text = parse_time(args, expect_time_keyword_at_start=True)
        if remind_time is False:
            # Time parsing failed, treat entire args as message
            message_text = ' '.join(args).strip()
            remind_time = None

        # Validate message text
        if not message_text:
            await ctx.send(f"@{ctx.author.name}, please provide a message for the reminder.")
            return

        # Create a unique reminder ID
        reminder_id = str(uuid.uuid4())[:8]

        # Get the channel where the command was used
        channel = ctx.channel
        channel_name = channel.name

        # Fetch channel user ID
        channel_user = await fetch_user(self.bot, channel_name)
        if not channel_user:
            await ctx.send(f"@{ctx.author.name}, failed to fetch channel information.")
            return
        channel_id = channel_user.id

        # Determine if it's a trigger_on_message reminder
        trigger_on_message = remind_time is None

        # Create the Reminder object
        reminder = Reminder(
            reminder_id=reminder_id,
            user=ctx.author,
            target=target,
            message=message_text,
            channel_id=channel_id,
            channel_name=channel_name,
            remind_time=remind_time,
            private=False,
            trigger_on_message=trigger_on_message
        )

        # Store the reminder in the database
        conn = get_database_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO reminders (id, user_id, username, target_id, target_name, channel_id, channel_name,
            message, remind_time, private, trigger_on_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
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
            int(reminder.trigger_on_message)
        ))
        conn.commit()
        conn.close()
        self.logger.debug(f"Stored reminder {reminder.id}: {reminder.__dict__}")

        # Confirm to the user
        if remind_time:
            time_formatted = format_time_delta(remind_time - datetime.now(timezone.utc))
            await ctx.send(f"@{ctx.author.name}, I will remind @{target.name} in {time_formatted} - {message_text}. ID: {reminder.id}")
        else:
            await ctx.send(f"@{ctx.author.name}, I will remind @{target.name} on their next message - {message_text}. ID: {reminder.id}")

    @commands.command(name='remindme')
    async def remindme(self, ctx: commands.Context, *args):
        """
        Sets a reminder for yourself.

        Usage:
        - #remindme [in/on/after time] message
        """
        self.logger.info(f"Processing command 'remindme' from {ctx.author.name}: Args={args}")

        if not args:
            await ctx.send(f"@{ctx.author.name}, please provide a message for the reminder.")
            return

        # Parse time and message
        remind_time, message_text = parse_time(args, expect_time_keyword_at_start=True)
        if remind_time is False:
            # Time parsing failed, treat entire args as message
            message_text = ' '.join(args).strip()
            remind_time = None

        # Validate message text
        if not message_text:
            await ctx.send(f"@{ctx.author.name}, please provide a message for the reminder.")
            return

        # Create a unique reminder ID
        reminder_id = str(uuid.uuid4())[:8]

        # Get the channel where the command was used
        channel = ctx.channel
        channel_name = channel.name

        # Fetch channel user ID
        channel_user = await fetch_user(self.bot, channel_name)
        if not channel_user:
            await ctx.send(f"@{ctx.author.name}, failed to fetch channel information.")
            return
        channel_id = channel_user.id

        # Determine if it's a trigger_on_message reminder
        trigger_on_message = remind_time is None

        # Create the Reminder object
        reminder = Reminder(
            reminder_id=reminder_id,
            user=ctx.author,
            target=ctx.author,
            message=message_text,
            channel_id=channel_id,
            channel_name=channel_name,
            remind_time=remind_time,
            private=False,
            trigger_on_message=trigger_on_message
        )

        # Store the reminder in the database
        conn = get_database_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO reminders (id, user_id, username, target_id, target_name, channel_id, channel_name,
            message, remind_time, private, trigger_on_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
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
            int(reminder.trigger_on_message)
        ))
        conn.commit()
        conn.close()
        self.logger.debug(f"Stored reminder {reminder.id}: {reminder.__dict__}")

        # Confirm to the user
        if remind_time:
            time_formatted = format_time_delta(remind_time - datetime.now(timezone.utc))
            await ctx.send(f"@{ctx.author.name}, I will remind you in {time_formatted} - {message_text}. ID: {reminder.id}")
        else:
            await ctx.send(f"@{ctx.author.name}, I will remind you on your next message - {message_text}. ID: {reminder.id}")

    @commands.command(name='unset')
    async def unset(self, ctx: commands.Context, *, arg: str = None):
        """
        Unsets a reminder by ID or 'last'.

        Usage:
        - #unset reminder (ID)
        - #unset reminder last
        """
        if not arg:
            await ctx.send(f"@{ctx.author.name}, please provide the ID of the reminder to unset.")
            return

        parts = arg.split()
        if len(parts) != 2 or parts[0].lower() != 'reminder':
            await ctx.send(f"@{ctx.author.name}, please use the format: #unset reminder (ID)")
            return

        identifier = parts[1].lower()
        reminder = None

        conn = get_database_connection(self.db_path)
        cursor = conn.cursor()
        if identifier == 'last':
            # Find the last reminder set by the user or for the user
            cursor.execute('''
                SELECT * FROM reminders
                WHERE (user_id = ? OR target_id = ?) AND active = 1
                ORDER BY rowid DESC
                LIMIT 1
            ''', (ctx.author.id, ctx.author.id))
        else:
            # Find by ID
            cursor.execute('SELECT * FROM reminders WHERE id = ? AND active = 1', (identifier,))

        row = cursor.fetchone()
        conn.close()

        if row:
            if len(row) != 12:
                self.logger.error(f"Unexpected number of columns in row: {row}")
                await ctx.send(f"@{ctx.author.name}, failed to unset the reminder due to an error.")
                return
            reminder_id, user_id_db, username, target_id, target_name, channel_id, channel_name, message_text, remind_time_str, private, trigger_on_message, active = row

            # Ensure the user has permission to unset the reminder
            if str(user_id_db) != str(ctx.author.id) and str(target_id) != str(ctx.author.id):
                await ctx.send(f"@{ctx.author.name}, you can only unset your own reminders or reminders set for you.")
                return

            # Remove the reminder from the database
            remove_reminder(reminder_id, self.db_path)

            # Send confirmation in the appropriate channel
            channel = get_channel(self.bot, channel_name)
            if channel:
                await channel.send(f"@{ctx.author.name}, reminder '{reminder_id}' has been unset.")
            else:
                await ctx.send(f"@{ctx.author.name}, reminder '{reminder_id}' has been unset.")
        else:
            await ctx.send(f"@{ctx.author.name}, no reminder found with ID '{identifier}'.")

    @commands.command(name='listreminders')
    async def listreminders(self, ctx: commands.Context):
        """
        Lists all active reminders for the user.

        Usage:
        - #listreminders
        """
        conn = get_database_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, message, remind_time, trigger_on_message FROM reminders
            WHERE (user_id = ? OR target_id = ?) AND active = 1
            ORDER BY remind_time ASC
        ''', (ctx.author.id, ctx.author.id))
        rows = cursor.fetchall()
        conn.close()

        if rows:
            reminders = []
            for row in rows:
                reminder_id, message_text, remind_time_str, trigger_on_message = row
                if remind_time_str:
                    try:
                        remind_time = datetime.fromisoformat(remind_time_str)
                        if remind_time.tzinfo is None:
                            remind_time = remind_time.replace(tzinfo=timezone.utc)
                        time_remaining = remind_time - datetime.now(timezone.utc)
                        time_formatted = format_time_delta(time_remaining)
                    except (TypeError, ValueError):
                        time_formatted = 'Unknown time'
                elif trigger_on_message:
                    time_formatted = 'On next message'
                else:
                    time_formatted = 'Unknown time'
                reminders.append(f"ID: {reminder_id}, In: {time_formatted}, Message: {message_text}")
            reminders_text = ' | '.join(reminders)
            await ctx.send(f"@{ctx.author.name}, your active reminders: {reminders_text}")
        else:
            await ctx.send(f"@{ctx.author.name}, you have no active reminders.")

    @commands.command(name='modifyreminder')
    async def modifyreminder(self, ctx: commands.Context, reminder_id: str, *, new_message: str = None):
        """
        Modifies an existing reminder.

        Usage:
        - #modifyreminder (ID) new message
        """
        if not reminder_id or not new_message:
            await ctx.send(f"@{ctx.author.name}, please provide the ID of the reminder and the new message.")
            return

        conn = get_database_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM reminders WHERE id = ? AND active = 1', (reminder_id,))
        row = cursor.fetchone()

        if row:
            reminder_id_db, user_id_db, username, target_id, target_name, channel_id, channel_name, message_text, remind_time_str, private, trigger_on_message, active = row

            # Ensure the user has permission to modify the reminder
            if str(user_id_db) != str(ctx.author.id):
                await ctx.send(f"@{ctx.author.name}, you can only modify your own reminders.")
                conn.close()
                return

            # Update the reminder message
            cursor.execute('UPDATE reminders SET message = ? WHERE id = ?', (new_message, reminder_id))
            conn.commit()
            conn.close()
            await ctx.send(f"@{ctx.author.name}, reminder '{reminder_id}' has been updated.")
        else:
            conn.close()
            await ctx.send(f"@{ctx.author.name}, no active reminder found with ID '{reminder_id}'.")

    def log_missing_data(self, message):
        """Logs messages with missing data."""
        self.logger.warning(
            f"Received a message with missing data. Content: {getattr(message, 'content', 'None')}, "
            f"Channel: {getattr(message.channel, 'name', 'None')}"
        )


def setup(bot: commands.Bot):
    bot.add_cog(Remind(bot))
