from twitchio.ext import commands
from datetime import datetime, timezone
import logging
from collections import defaultdict


class LastMessage(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("twitch_bot.last_message")
        self.last_messages = defaultdict(lambda: defaultdict(dict))

    @commands.Cog.event()
    async def event_message(self, message):
        if message.echo:
            return

        channel_name = message.channel.name if message.channel else "Unknown Channel"
        timestamp = datetime.now(timezone.utc)

        self.last_messages[channel_name][message.author.name.lower()] = {
            "content": message.content,
            "timestamp": timestamp,
        }

        log_entry = f"{channel_name} - {message.author.name}: {message.content}"
        self.logger.info(log_entry)

    @commands.command(name="lastmessage", aliases=["lm"])
    async def last_message_command(self, ctx, username: str):
        channel_name = ctx.channel.name
        username = username.lower()

        if username not in self.last_messages[channel_name]:
            await ctx.send(f"@{ctx.author.name}, no messages found from {username} in this channel.")
            return

        last_message = self.last_messages[channel_name][username]
        content = last_message["content"]
        timestamp = last_message["timestamp"]
        time_ago = self.format_time_ago(timestamp)

        response = f'@{ctx.author.name}, last message from {username}: "{content}" (sent {time_ago})'
        await ctx.send(response)

    def format_time_ago(self, timestamp):
        now = datetime.now(timezone.utc)
        delta = now - timestamp

        if delta.total_seconds() < 60:
            return f"{int(delta.total_seconds())} seconds ago"
        elif delta.total_seconds() < 3600:
            minutes = int(delta.total_seconds() / 60)
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif delta.total_seconds() < 86400:
            hours = int(delta.total_seconds() / 3600)
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        else:
            days = delta.days
            return f"{days} day{'s' if days != 1 else ''} ago"


def prepare(bot):
    bot.add_cog(LastMessage(bot))
