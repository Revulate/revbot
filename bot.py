import os
import asyncio
import random
import json
from datetime import datetime, timedelta
from twitchio.ext import commands
from twitchio import AuthenticationError
from dotenv import load_dotenv, set_key
from logger import logger
from utils import CustomContext
from twitch_helix_client import TwitchAPI
import aiohttp
import sys
import codecs

sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

# Load environment variables
load_dotenv()

# List of cogs
COGS = [
    "cogs.roll",
    "cogs.rate",
    "cogs.afk",
    "cogs.preview",
    "cogs.remind",
    "cogs.admin",
    "cogs.gpt",
    "cogs.spc",
    "cogs.user",
    "cogs.lastmessage",
    "cogs.dvp",
    "cogs.uptime",
    "cogs.stats",
]


class TwitchBot(commands.Bot):
    def __init__(self):
        self.logger = logger

        # Use environment variables
        self.token = os.getenv("ACCESS_TOKEN")
        self.client_id = os.getenv("TWITCH_CLIENT_ID")
        self.client_secret = os.getenv("TWITCH_CLIENT_SECRET")
        self.refresh_token_string = os.getenv("REFRESH_TOKEN")
        nick = os.getenv("BOT_NICK")
        prefix = os.getenv("COMMAND_PREFIX", "#")
        channels = os.getenv("TWITCH_CHANNELS", "").split(",")

        # Check for missing critical environment variables
        self._check_env_variables()

        super().__init__(
            token=self.token,
            client_id=self.client_id,
            nick=nick,
            prefix=prefix,
            initial_channels=[channel.strip() for channel in channels if channel.strip()],
        )
        self.broadcaster_user_id = os.getenv("BROADCASTER_USER_ID")
        self.bot_user_id = None
        self.context_class = CustomContext
        self.http_session = None
        self.token_file = "twitch_tokens.json"
        self.token_check_task = None

        # Initialize TwitchAPI
        redirect_uri = "http://localhost:3000"  # or whatever you used during authentication
        self.twitch_api = TwitchAPI(self.client_id, self.client_secret, redirect_uri)
        self.twitch_api.oauth_token = self.token
        self.twitch_api.refresh_token = self.refresh_token_string
        self.logger.info("TwitchAPI instance created and tokens saved")

    async def event_ready(self):
        self.logger.info(f"Logged in as | {self.nick}")
        self.load_tokens_from_file()
        await self.ensure_valid_token()
        await self.fetch_user_id()
        await self.fetch_example_streams()
        self.load_modules()

        # Start periodic token checking
        self.token_check_task = asyncio.create_task(self.check_token_regularly())

        # Test API call
        try:
            user_info = await self.twitch_api.get_users([self.nick])
            self.logger.info(f"Successfully fetched user info: {user_info}")
        except Exception as e:
            self.logger.error(f"Error fetching user info: {e}")

        # Check token status
        self.logger.info(f"Current access token: {self.twitch_api.oauth_token[:10]}...")
        self.logger.info(
            f"Current refresh token: {self.twitch_api.refresh_token[:10]}..."
            if self.twitch_api.refresh_token
            else "No refresh token"
        )
        self.logger.info(f"Token expiry: {self.twitch_api.token_expiry}")

    async def check_token_regularly(self):
        while True:
            await asyncio.sleep(3600)  # Check every hour
            await self.ensure_valid_token()

    async def ensure_valid_token(self):
        if not self.twitch_api.token_expiry or datetime.now() >= self.twitch_api.token_expiry - timedelta(minutes=10):
            self.logger.info("Token expired or close to expiry. Refreshing...")
            await self.refresh_token()

    async def refresh_token(self):
        self.logger.info("Refreshing access token...")
        success = await self.twitch_api.refresh_oauth_token()
        if success:
            self.token = self.twitch_api.oauth_token
            self.refresh_token_string = self.twitch_api.refresh_token
            self.logger.info("Access token refreshed successfully")

            # Update .env file
            set_key(".env", "ACCESS_TOKEN", self.token)
            set_key(".env", "REFRESH_TOKEN", self.refresh_token_string)

            # Update JSON file
            self.update_token_file()

            # Reload environment variables
            load_dotenv(override=True)
        else:
            self.logger.error("Failed to refresh access token")
        return success

    def update_token_file(self):
        token_data = {
            "access_token": self.token,
            "refresh_token": self.refresh_token_string,
            "expiry": self.twitch_api.token_expiry.isoformat() if self.twitch_api.token_expiry else None,
        }
        with open(self.token_file, "w") as f:
            json.dump(token_data, f)

    def load_tokens_from_file(self):
        if os.path.exists(self.token_file):
            with open(self.token_file, "r") as f:
                token_data = json.load(f)
            self.token = token_data.get("access_token")
            self.refresh_token_string = token_data.get("refresh_token")
            expiry = token_data.get("expiry")
            if expiry:
                self.twitch_api.token_expiry = datetime.fromisoformat(expiry)

    def _check_env_variables(self):
        """Check for missing critical environment variables."""
        required_vars = ["ACCESS_TOKEN", "TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET", "BOT_NICK", "REFRESH_TOKEN"]
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            error_msg = f"The following environment variables are missing: {', '.join(missing_vars)}"
            self.logger.error(error_msg)
            raise ValueError(error_msg)

    async def fetch_user_id(self):
        retries = 3
        base_delay = 5
        for attempt in range(1, retries + 1):
            try:
                users = await self.fetch_users(names=[self.nick])
                if users:
                    self.bot_user_id = users[0].id
                    self.logger.info(f"User ID is | {self.bot_user_id}")
                    return
                else:
                    self.logger.error("Failed to fetch user data.")
            except Exception as e:
                self.logger.error(f"Attempt {attempt} - Error fetching user data: {e}", exc_info=True)

            if attempt < retries:
                delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1)
                self.logger.info(f"Retrying to fetch user data in {delay:.2f} seconds...")
                await asyncio.sleep(delay)

        self.logger.error("Exceeded maximum retries to fetch user data.")

    async def fetch_example_streams(self):
        try:
            streams = await self.twitch_api.get_streams(["afro", "cohhcarnage"])
            for stream in streams.get("data", []):
                self.logger.info(
                    f"Stream found: {stream.get('user_name')} is live with {stream.get('viewer_count')} viewers."
                )
        except Exception as e:
            self.logger.error(f"Error fetching streams: {e}", exc_info=True)

    def load_modules(self):
        for cog in COGS:
            try:
                self.logger.info(f"Attempting to load extension: {cog}")
                self.load_module(cog)
                self.logger.info(f"Loaded extension: {cog}")
            except Exception as e:
                self.logger.error(f"Failed to load extension {cog}: {e}")

    @commands.command(name="listcommands")
    async def list_commands(self, ctx: commands.Context):
        command_list = [cmd.name for cmd in self.commands.values()]
        await ctx.send(f"Available commands: {', '.join(command_list)}")

    async def event_error(self, error: Exception, data: str = None):
        """
        Handles errors in the bot's event loop.
        """
        self.logger.error(f"Error in event loop: {error}")
        self.logger.error(f"Error traceback: {traceback.format_exc()}")
        if data:
            self.logger.error(f"Error data: {data}")


async def main():
    load_dotenv()
    bot = TwitchBot()

    while True:
        try:
            await bot.start()
        except AuthenticationError:
            logger.error("Authentication failed. Refreshing token and retrying...")
            await bot.twitch_api.refresh_oauth_token()
            continue
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
            logger.error(f"Error traceback: {traceback.format_exc()}")
            logger.info("Attempting to restart the bot in 60 seconds...")
            await asyncio.sleep(60)
        else:
            break


if __name__ == "__main__":
    asyncio.run(main())
