import os
from dotenv import load_dotenv
import aiohttp
import datetime
from twitchio.ext import commands
from asyncio import Semaphore

load_dotenv()

class Preview(commands.Cog):
    """Cog for displaying the preview thumbnail and details of a specified Twitch stream."""

    RATE_LIMIT = Semaphore(1)  # Limit to 1 concurrent request per user to prevent rate limiting

    def __init__(self, bot):
        self.bot = bot
        self.client_id = os.getenv("CLIENT_ID", "")
        self.oauth_token = None

    async def get_oauth_token(self):
        """Fetch OAuth token for Twitch API."""
        if not self.oauth_token:
            self.oauth_token = os.getenv("TWITCH_OAUTH_TOKEN")
            if not self.oauth_token:
                raise ValueError("Twitch OAuth token must be set.")
        print("[DEBUG] OAuth token retrieved.")
        return self.oauth_token

    async def get_channel_info(self, channel_name):
        """Fetch channel information from Twitch API."""
        token = await self.get_oauth_token()
        url = f"https://api.twitch.tv/helix/search/channels?query={channel_name}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Client-ID": self.client_id
        }
        print(f"[DEBUG] Requesting channel info for '{channel_name}' with URL: {url}")
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                print(f"[DEBUG] Received response status: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    print(f"[DEBUG] Channel info data: {data}")
                    channels = data.get("data", [])
                    for channel in channels:
                        if channel.get("broadcaster_login", "").lower() == channel_name.lower():
                            return channel
                elif response.status == 401:
                    self.oauth_token = None  # Reset the token to force refresh
                    print("[ERROR] Unauthorized request. Token might be expired.")
                else:
                    print(f"[ERROR] Failed to fetch channel info: {response.status}")
                return None

    async def get_stream_info(self, user_id):
        """Fetch stream information from Twitch API."""
        token = await self.get_oauth_token()
        url = f"https://api.twitch.tv/helix/streams?user_id={user_id}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Client-ID": self.client_id
        }
        print(f"[DEBUG] Requesting stream info for user_id '{user_id}' with URL: {url}")
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                print(f"[DEBUG] Received response status: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    print(f"[DEBUG] Stream info data: {data}")
                    streams = data.get("data", [])
                    if streams:
                        return streams[0]
                elif response.status == 401:
                    self.oauth_token = None  # Reset the token to force refresh
                    print("[ERROR] Unauthorized request. Token might be expired.")
                else:
                    print(f"[ERROR] Failed to fetch stream info: {response.status}")
                return None

    @commands.command(name="preview")
    async def preview_command(self, ctx: commands.Context, channel_name: str):
        """
        Posts the preview thumbnail link and details of the specified Twitch stream.
        Usage: #preview <channel_name>
        """
        async with self.RATE_LIMIT:
            if not channel_name:
                await ctx.send(f"@{ctx.author.name}, please provide a channel name to get the preview thumbnail.")
                return

            print(f"[DEBUG] Getting channel info for '{channel_name}'")
            channel_info = await self.get_channel_info(channel_name)
            if channel_info is None or 'id' not in channel_info:
                await ctx.send(f"@{ctx.author.name}, could not retrieve valid channel information for '{channel_name}'. Please ensure the channel name is correct or check if your Twitch credentials are properly set.")
                return

            user_id = channel_info.get("id")
            if user_id is None:
                await ctx.send(f"@{ctx.author.name}, channel information for '{channel_name}' is incomplete. Unable to retrieve user ID.")
                return

            is_live = channel_info.get("is_live", False)
            title = channel_info.get("title", "Unknown")
            preview_url = f"https://static-cdn.jtvnw.net/previews-ttv/live_user_{channel_name.lower()}.jpg"

            if is_live:
                print(f"[DEBUG] Channel '{channel_name}' is live. Fetching stream info.")
                stream_info = await self.get_stream_info(user_id)
                if stream_info is None:
                    await ctx.send(f"@{ctx.author.name}, no live stream data available for '{channel_name}'.")
                    return

                viewer_count = stream_info.get("viewer_count", 0)
                started_at = stream_info.get("started_at")
                if started_at:
                    start_time = datetime.datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                    time_live = datetime.datetime.now(datetime.timezone.utc) - start_time
                    await ctx.send(
                        f"@{ctx.author.name}, {channel_name} is live! Title: {title}, Viewers: {viewer_count}, Live for: {time_live}. Preview: {preview_url}"
                    )
                    print(f"[DEBUG] Sent live stream info for '{channel_name}' to chat.")
                else:
                    await ctx.send(f"@{ctx.author.name}, {channel_name} is live but the start time is unavailable. Preview: {preview_url}")
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
                print(f"[DEBUG] Sent offline info for '{channel_name}' to chat.")

def prepare(bot):
    bot.add_cog(Preview(bot))