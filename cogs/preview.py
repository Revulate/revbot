import os
import aiohttp
import datetime
from twitchio.ext import commands

class Preview(commands.Cog):
    """Cog for displaying the preview thumbnail and details of a specified Twitch stream."""

    def __init__(self, bot):
        self.bot = bot
        self.client_id = os.getenv("TWITCH_CLIENT_ID", "")
        self.client_secret = os.getenv("TWITCH_CLIENT_SECRET", "")
        self.oauth_token = None

    async def get_oauth_token(self):
        """Fetch OAuth token for Twitch API."""
        if not self.client_id or not self.client_secret:
            raise ValueError("Twitch client ID and client secret must be set.")
        if self.oauth_token:
            return self.oauth_token

        url = "https://id.twitch.tv/oauth2/token"
        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials"
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    self.oauth_token = data.get("access_token")
                    return self.oauth_token
                else:
                    raise Exception("Failed to get OAuth token from Twitch API.")

    async def get_channel_info(self, channel_name):
        """Fetch channel information from Twitch API."""
        token = await self.get_oauth_token()
        url = f"https://api.twitch.tv/helix/search/channels?query={channel_name}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Client-ID": self.client_id
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    channels = data.get("data", [])
                    for channel in channels:
                        if channel.get("broadcaster_login", "").lower() == channel_name.lower():
                            return channel
                return None

    async def get_stream_info(self, user_id):
        """Fetch stream information from Twitch API."""
        token = await self.get_oauth_token()
        url = f"https://api.twitch.tv/helix/streams?user_id={user_id}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Client-ID": self.client_id
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    streams = data.get("data", [])
                    if streams:
                        return streams[0]
                return None

    @commands.command(name="preview")
    async def preview_command(self, ctx: commands.Context, channel_name: str):
        """
        Posts the preview thumbnail link and details of the specified Twitch stream.
        Usage: #preview <channel_name>
        """
        if not channel_name:
            await ctx.send(f"@{ctx.author.name}, please provide a channel name to get the preview thumbnail.")
            return

        channel_info = await self.get_channel_info(channel_name)
        if not channel_info:
            await ctx.send(f"@{ctx.author.name}, could not find channel information for '{channel_name}'. Please ensure the channel name is correct.")
            return

        user_id = channel_info.get("id")
        is_live = channel_info.get("is_live", False)
        title = channel_info.get("title", "Unknown")
        preview_url = f"https://static-cdn.jtvnw.net/previews-ttv/live_user_{channel_name.lower()}.jpg"

        if is_live:
            stream_info = await self.get_stream_info(user_id)
            if stream_info:
                viewer_count = stream_info.get("viewer_count", 0)
                started_at = stream_info.get("started_at")
                start_time = datetime.datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                time_live = datetime.datetime.now(datetime.timezone.utc) - start_time
                await ctx.send(
                    f"@{ctx.author.name}, {channel_name} is live! Title: {title}, Viewers: {viewer_count}, Live for: {time_live}. Preview: {preview_url}"
                )
            else:
                await ctx.send(f"@{ctx.author.name}, could not retrieve stream info for {channel_name}.")
        else:
            last_live = channel_info.get("started_at") or None
            if last_live:
                last_live_time = datetime.datetime.fromisoformat(last_live.replace("Z", "+00:00"))
                time_since_live = datetime.datetime.now(datetime.timezone.utc) - last_live_time
                await ctx.send(
                    f"@{ctx.author.name}, {channel_name} is currently offline. Last live: {time_since_live} ago. Preview: {preview_url}"
                )
            else:
                await ctx.send(f"@{ctx.author.name}, {channel_name} is currently offline. Preview: {preview_url}")

def prepare(bot):
    bot.add_cog(Preview(bot))