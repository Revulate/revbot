# cogs/lastmessage.py
from twitchio.ext import commands
from datetime import datetime, timezone
from utils import normalize_username


class LastMessage(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="lastmessage", aliases=["lm"])
    async def last_message_command(self, ctx, username: str):
        username = normalize_username(username)
        message_logger = self.bot.get_cog("MessageLogger")
        if not message_logger:
            await ctx.send("Message logging system is not available.")
            return

        result = await message_logger.get_last_message(ctx.channel.name, username.lower())
        if result:
            last_message, timestamp = result
            time_ago = self.format_time_ago(datetime.fromisoformat(timestamp))
            response = f'@{ctx.author.name}, last message from {username}: "{last_message}" (sent {time_ago})'
        else:
            response = f"@{ctx.author.name}, no messages found from {username} in this channel."

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
