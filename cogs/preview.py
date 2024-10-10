import os
from dotenv import load_dotenv
import aiohttp
import datetime
from twitchio.ext import commands
from asyncio import Semaphore, sleep

load_dotenv()

class Preview(commands.Cog):
    """Cog for displaying the preview thumbnail and details of a specified Twitch stream."""

    RATE_LIMIT = Semaphore(1)  # Limit to 1 concurrent request per user to prevent rate limiting

    def __init__(self, bot):
        self.bot = bot
        self.client_id = os.getenv("CLIENT_ID")
        if not self.client_id:
            raise ValueError("CLIENT_ID must be set in the environment variables.")
        self.oauth_token = None
        self.token_expiry = None

    async def get_oauth_token(self):
        """Fetch OAuth token for Twitch API."""
        # Refresh token if expired
        if not self.oauth_token or (self.token_expiry and datetime.datetime.now() >= self.token_expiry):
            
            self.bot.logger.debug(f"OAuth token retrieved and valid until: {self.token_expiry}")
        else:
            raise ValueError("Failed to retrieve OAuth token. Please check your credentials.")
        return self.oauth_token

    async def get_channel_info(self, channel_name):
        """Fetch channel information from Twitch API."""
        token = await self.get_oauth_token()
        url = f"https://api.twitch.tv/helix/users?login={channel_name}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Client-ID": self.client_id
        }
        self.bot.logger.debug(f"Requesting channel info for '{channel_name}' with URL: {url}")
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                self.bot.logger.debug(f"Received response status: {response.status}")
                response_text = await response.text()
                self.bot.logger.debug(f"Response content: {response_text}")
                if response.status == 200:
                    data = await response.json()
                    self.bot.logger.debug(f"Channel info data: {data}")
                    users = data.get("data", [])
                    if users:
                        return users[0]
                elif response.status == 401:
                    self.oauth_token = None  # Reset the token to force refresh
                    self.bot.logger.error("Unauthorized request. Token might be expired.")
                else:
                    self.bot.logger.error(f"Failed to fetch channel info: {response.status}")
                return None

    async def get_stream_info(self, user_login):
        """Fetch stream information from Twitch API."""
        token = await self.get_oauth_token()
        url = f"https://api.twitch.tv/helix/streams?user_login={user_login}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Client-ID": self.client_id
        }
        self.bot.logger.debug(f"Requesting stream info for user_login '{user_login}' with URL: {url}")
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                self.bot.logger.debug(f"Received response status: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    self.bot.logger.debug(f"Stream info data: {data}")
                    streams = data.get("data", [])
                    if streams:
                        return streams[0]
                elif response.status == 401:
                    self.oauth_token = None  # Reset the token to force refresh
                    self.bot.logger.error("Unauthorized request. Token might be expired.")
                else:
                    self.bot.logger.error(f"Failed to fetch stream info: {response.status}")
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

            retry_count = 3
            for attempt in range(retry_count):
                try:
                    self.bot.logger.debug(f"Getting channel info for '{channel_name}' (Attempt {attempt + 1})")
                    channel_info = await self.get_channel_info(channel_name)
                    if channel_info is None or not channel_info.get('id'):
                        self.bot.logger.error(f"Invalid or missing channel information for '{channel_name}'. Channel info: {channel_info}")
                        await ctx.send(f"@{ctx.author.name}, could not retrieve valid channel information for '{channel_name}'. Please ensure the channel name is correct or check if your Twitch credentials are properly set.")
                        return

                    user_login = channel_info.get("login")
                    if not user_login:
                        self.bot.logger.error(f"Missing login information for '{channel_name}'. Channel info: {channel_info}")
                        await ctx.send(f"@{ctx.author.name}, channel information for '{channel_name}' is incomplete. Unable to retrieve user login.")
                        return
                    

                    is_live = await self.get_stream_info(user_login) is not None
                    title = channel_info.get("description", "No title available")
                    preview_url = f"https://static-cdn.jtvnw.net/previews-ttv/live_user_{channel_name.lower()}.jpg"

                    if is_live:
                        self.bot.logger.debug(f"Channel '{channel_name}' is live. Fetching stream info.")
                        stream_info = await self.get_stream_info(user_login)
                        if stream_info is None:
                            await ctx.send(f"@{ctx.author.name}, no live stream data available for '{channel_name}'.")
                            return

                        viewer_count = stream_info.get("viewer_count", 0)
                        if viewer_count is None:
                            viewer_count = 0
                        started_at = stream_info.get("started_at")
                        if started_at:
                            start_time = datetime.datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                            time_live = datetime.datetime.now(datetime.timezone.utc) - start_time
                            await ctx.send(
                                f"@{ctx.author.name}, {channel_name} is live! Title: {title}, Viewers: {viewer_count}, Live for: {time_live}. Preview: {preview_url}"
                            )
                            self.bot.logger.debug(f"Sent live stream info for '{channel_name}' to chat.")
                        else:
                            await ctx.send(f"@{ctx.author.name}, {channel_name} is live but the start time is unavailable. Preview: {preview_url}")
                    else:
                        await ctx.send(f"@{ctx.author.name}, {channel_name} is currently offline. Preview: {preview_url}")
                        self.bot.logger.debug(f"Sent offline info for '{channel_name}' to chat.")
                    break
                except Exception as e:
                    self.bot.logger.error(f"Attempt {attempt + 1} failed with error: {e}")
                    if attempt < retry_count - 1:
                        await sleep(2)  # Wait before retrying
                    else:
                        await ctx.send(f"@{ctx.author.name}, an error occurred while processing your request. Please try again later.")


def prepare(bot):
    bot.add_cog(Preview(bot))