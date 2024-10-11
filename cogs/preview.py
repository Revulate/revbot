# cogs/preview.py

import os
from dotenv import load_dotenv
import aiohttp
from twitchio.ext import commands
from asyncio import sleep
from datetime import datetime, timezone

load_dotenv()

class Preview(commands.Cog):
    """Cog for displaying the preview thumbnail and details of a specified Twitch stream."""

    def __init__(self, bot):
        self.bot = bot
        self.client_id = os.getenv("TWITCH_CLIENT_ID")
        self.client_secret = os.getenv("TWITCH_CLIENT_SECRET")
        if not self.client_id or not self.client_secret:
            raise ValueError("TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET must be set in the environment variables.")

    async def get_channel_info(self, channel_name):
        """Fetch channel information from Twitch API."""
        users = await self.bot.fetch_users(names=[channel_name])
        if not users:
            return None

        user = users[0]
        streams = await self.bot.fetch_streams(user_logins=[channel_name])
        
        channel_info = {
            "id": user.id,
            "name": user.name,
            "is_live": False,
            "viewer_count": 0,
            "title": "Offline",
            "game_name": "N/A",
            "thumbnail_url": f"https://static-cdn.jtvnw.net/previews-ttv/live_user_{channel_name.lower()}.jpg",
            "started_at": None
        }

        if streams:
            stream = streams[0]
            channel_info.update({
                "is_live": True,
                "viewer_count": stream.viewer_count,
                "title": stream.title,
                "game_name": stream.game_name,
                "started_at": stream.started_at
            })

        return channel_info

    def format_duration(self, duration):
        """Format timedelta into a human-readable string."""
        days, seconds = duration.days, duration.seconds
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        
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

    @commands.command(name="preview")
    async def preview_command(self, ctx: commands.Context, channel_name: str):
        """
        Posts the preview thumbnail and stream details of the specified Twitch channel.
        Usage: #preview <channel_name>
        """
        if not channel_name:
            await ctx.send(f"@{ctx.author.name}, please provide a channel name to get the preview information.")
            return

        retry_count = 3
        for attempt in range(retry_count):
            try:
                self.bot.logger.debug(f"Getting info for channel '{channel_name}' (Attempt {attempt + 1})")
                channel_info = await self.get_channel_info(channel_name)
                
                if not channel_info:
                    self.bot.logger.error(f"Invalid or missing channel information for '{channel_name}'.")
                    await ctx.send(f"@{ctx.author.name}, could not retrieve valid channel information for '{channel_name}'. Please ensure the channel name is correct.")
                    return

                now = datetime.now(timezone.utc)
                if channel_info["is_live"]:
                    duration = now - channel_info["started_at"]
                    status = f"LIVE ({self.format_duration(duration)})"
                    viewers = f"{channel_info['viewer_count']:,} viewers"
                    response = (
                        f"@{ctx.author.name}, Channel: https://twitch.tv/{channel_info['name']} | "
                        f"Status: {status} | "
                        f"Viewers: {viewers} | "
                        f"Category: {channel_info['game_name']} | "
                        f"Title: {channel_info['title']} | "
                        f"Preview: {channel_info['thumbnail_url']}"
                    )
                else:
                    status = "OFFLINE"
                    response = (
                        f"@{ctx.author.name}, Channel: https://twitch.tv/{channel_info['name']} | "
                        f"Status: {status}"
                    )

                await ctx.send(response)
                self.bot.logger.debug(f"Sent preview info for '{channel_name}' to chat.")
                break
            except Exception as e:
                self.bot.logger.error(f"Attempt {attempt + 1} failed with error: {e}")
                if attempt < retry_count - 1:
                    await sleep(2)  # Wait before retrying
                else:
                    await ctx.send(f"@{ctx.author.name}, an error occurred while processing your request. Please try again later.")

def prepare(bot):
    bot.add_cog(Preview(bot))