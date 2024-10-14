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
    def __init__(self, loop):
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
            loop=loop,
        )
        self.broadcaster_user_id = os.getenv("BROADCASTER_USER_ID")
        self.bot_user_id = None
        self.context_class = CustomContext
        self.http_session = None
        self.token_check_task = None
        self.token_file = "twitch_tokens.json"

        # Initialize TwitchAPI
        redirect_uri = "http://localhost:3000"  # or whatever you used during authentication
        self.twitch_api = TwitchAPI(self.client_id, self.client_secret, redirect_uri)
        self.twitch_api.oauth_token = self.token
        self.twitch_api.refresh_token = self.refresh_token_string
        self.logger.info("TwitchAPI instance created and tokens saved")

    async def start(self):
        self.token_check_task = self.loop.create_task(self.check_token_regularly())
        await super().start()

    async def close(self):
        if self.token_check_task:
            self.token_check_task.cancel()
        await super().close()

    async def check_token_regularly(self):
        while True:
            await self.ensure_valid_token()
            await asyncio.sleep(3600)  # Check every hour

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
            self._connection._token = self.token
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

    async def event_ready(self):
        self.logger.info(f"Logged in as | {self.nick}")
        self.load_tokens_from_file()
        await self.ensure_valid_token()
        await self.fetch_user_id()
        await self.fetch_example_streams()
        self.load_modules()

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

    async def run(self):
        """Run the bot with authentication setup and error handling."""
        try:
            await self.create_session()
            while True:
                try:
                    await self.start()
                except AuthenticationError as e:
                    self.logger.error(f"Authentication Error: {e}. Attempting to refresh token...")
                    self.logger.debug(f"Type of self.refresh_token: {type(self.refresh_token)}")
                    if await self.refresh_token():
                        continue
                    else:
                        self.logger.error("Failed to refresh token. Exiting...")
                        break
                except Exception as e:
                    self.logger.error(f"An unexpected error occurred: {e}", exc_info=True)
                    await asyncio.sleep(60)  # Wait before attempting to restart
                else:
                    break  # If no exception occurs, break the loop
        finally:
            if self.http_session:
                await self.http_session.close()

    def _check_env_variables(self):
        """Check for missing critical environment variables."""
        required_vars = ["ACCESS_TOKEN", "TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET", "BOT_NICK", "REFRESH_TOKEN"]
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            error_msg = f"The following environment variables are missing: {', '.join(missing_vars)}"
            self.logger.error(error_msg)
            raise ValueError(error_msg)

    async def create_session(self):
        if self.http_session is None or self.http_session.closed:
            self.http_session = aiohttp.ClientSession()
        self.twitch_api.session = self.http_session

    async def event_channel_joined(self, channel):
        self.logger.info(f"Joined channel: {channel.name}")

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
                cog_name = cog.split(".")[-1]
                self.logger.info(f"Loaded extension: {cog_name}")

                # Log all commands after loading each cog
                all_commands = [cmd.name for cmd in self.commands.values() if isinstance(cmd, commands.Command)]
                self.logger.info(f"Current commands after loading {cog_name}: {', '.join(all_commands)}")

                # Get the cog instance using case-insensitive matching
                cog_instance = next((cog for name, cog in self.cogs.items() if name.lower() == cog_name.lower()), None)
                if cog_instance:
                    # Get commands associated with the cog
                    cog_commands = [cmd.name for cmd in self.commands.values() if cmd.cog == cog_instance]
                    if cog_commands:
                        self.logger.info(f"Commands added by {cog_name}: {', '.join(cog_commands)}")
                    else:
                        self.logger.warning(f"No commands found for cog {cog_name}")
                else:
                    self.logger.warning(f"Could not find cog instance for {cog_name}")
                    self.logger.debug(f"Available cogs: {list(self.cogs.keys())}")
            except Exception as e:
                self.logger.error(f"Failed to load extension {cog}: {e}", exc_info=True)

        # Log all commands after loading all cogs
        all_commands = [cmd.name for cmd in self.commands.values() if isinstance(cmd, commands.Command)]
        self.logger.info(f"All commands after loading all cogs: {', '.join(all_commands)}")

    @commands.command(name="listcommands")
    async def list_commands(self, ctx: commands.Context):
        command_list = [cmd.name for cmd in self.commands.values()]
        await ctx.send(f"Available commands: {', '.join(command_list)}")


async def main():
    loop = asyncio.get_event_loop()
    bot = TwitchBot(loop)

    try:
        await bot.run()
    except KeyboardInterrupt:
        await bot.close()
    finally:
        if bot.http_session:
            await bot.http_session.close()


if __name__ == "__main__":
    asyncio.run(main())
