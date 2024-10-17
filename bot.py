import os
import sys
import asyncio
import datetime
from twitchio.ext import commands
from dotenv import load_dotenv
from logger import log_info, log_error, log_warning, log_debug, get_logger, set_log_level
from utils import setup_database, get_database_connection
from twitch_helix_client import TwitchAPI

# Add the virtual environment's site-packages to sys.path
venv_path = os.getenv("PYTHONPATH")
if venv_path:
    sys.path.append(venv_path)

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
    "cogs.message_logger",
]


class TwitchBot(commands.Bot):
    def __init__(self):
        self.logger = get_logger("twitch_bot")
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        set_log_level(log_level)

        # Use environment variables
        self.client_id = os.getenv("TWITCH_CLIENT_ID")
        self.client_secret = os.getenv("TWITCH_CLIENT_SECRET")
        nick = os.getenv("BOT_NICK")
        prefix = os.getenv("COMMAND_PREFIX", "#")
        channels = os.getenv("TWITCH_CHANNELS", "").strip().split(",")
        self.initial_channels = [channel.strip() for channel in channels if channel.strip()]

        # Check for missing critical environment variables
        self._check_env_variables()

        # Initialize TwitchAPI
        redirect_uri = os.getenv("TWITCH_REDIRECT_URI", "http://localhost:3000")
        self.twitch_api = TwitchAPI(self.client_id, self.client_secret, redirect_uri)

        # Ensure token is valid before initializing the bot
        asyncio.create_task(self.twitch_api.ensure_token_valid())

        super().__init__(
            token=self.twitch_api.oauth_token,
            client_id=self.client_id,
            nick=nick,
            prefix=prefix,
            initial_channels=self.initial_channels,
        )
        self.broadcaster_user_id = os.getenv("BROADCASTER_USER_ID")
        self.bot_user_id = None
        self.http_session = None
        self.token_check_task = None

        log_info("TwitchAPI instance created and tokens saved")

        self._connection_retries = 0
        self._max_retries = 5
        self._closing = asyncio.Event()
        self.cog_tasks = []

    async def event_ready(self):
        log_info(f"Logged in as | {self.nick}")
        await self.twitch_api.ensure_token_valid()
        await self.fetch_user_id()
        await self.fetch_example_streams()
        self.load_modules()

        # Start periodic token checking
        self.token_check_task = asyncio.create_task(self.check_token_regularly())

        # Test API call
        try:
            user_info = await self.twitch_api.get_users([self.nick])
            log_info(f"Successfully fetched user info: {user_info}")
        except Exception as e:
            log_error(f"Error fetching user info: {e}")

        # Check token status
        log_info(f"Current access token: {self.twitch_api.oauth_token[:10]}...")
        log_info(
            f"Current refresh token: {self.twitch_api.refresh_token[:10]}..."
            if self.twitch_api.refresh_token
            else "No refresh token"
        )
        log_info(f"Token expiry: {self.twitch_api.token_expiry}")

    async def start(self):
        await self.twitch_api.ensure_token_valid()
        self.token = self.twitch_api.oauth_token  # Update the token before starting
        while self._connection_retries < self._max_retries:
            try:
                await super().start()
                break
            except Exception as e:
                self._connection_retries += 1
                log_error(f"Connection attempt {self._connection_retries} failed: {e}")
                if self._connection_retries < self._max_retries:
                    await asyncio.sleep(5 * self._connection_retries)  # Exponential backoff
                else:
                    log_error("Max retries reached. Unable to connect.")
                    raise

    async def close(self):
        self._closing.set()
        try:
            for task in self.cog_tasks:
                if task:
                    task.cancel()
            await asyncio.gather(*[t for t in self.cog_tasks if t], return_exceptions=True)

            if self._connection and hasattr(self._connection, "_close"):
                await self._connection._close()
            if hasattr(self, "_http") and self._http:
                await self._http.close()
            if self.http_session:
                await self.http_session.close()
            await self.twitch_api.close()
        except Exception as e:
            log_error(f"Error during close: {e}")
        finally:
            await super().close()

    async def _close_cogs(self):
        for name, cog in self.cogs.items():
            if hasattr(cog, "cog_unload") and asyncio.iscoroutinefunction(cog.cog_unload):
                try:
                    await cog.cog_unload()
                except Exception as e:
                    log_error(f"Error unloading cog {name}: {e}")

    def _check_env_variables(self):
        """Check for missing critical environment variables."""
        required_vars = ["TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET", "BOT_NICK"]
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            error_msg = f"The following environment variables are missing: {', '.join(missing_vars)}"
            log_error(error_msg)
            raise ValueError(error_msg)

    async def fetch_user_id(self):
        retries = 3
        base_delay = 5
        for attempt in range(1, retries + 1):
            try:
                users = await self.twitch_api.get_users([self.nick])
                if users and users.get("data"):
                    self.bot_user_id = users["data"][0]["id"]
                    log_info(f"User ID is | {self.bot_user_id}")
                    return
                else:
                    log_error("Failed to fetch user data.")
            except Exception as e:
                log_error(f"Attempt {attempt} - Error fetching user data: {e}", exc_info=True)

            if attempt < retries:
                delay = base_delay * (2 ** (attempt - 1))
                log_info(f"Retrying to fetch user data in {delay:.2f} seconds...")
                await asyncio.sleep(delay)

        log_error("Exceeded maximum retries to fetch user data.")

    async def fetch_example_streams(self):
        try:
            streams = await self.twitch_api.get_streams(["afro", "cohhcarnage"])
            for stream in streams.get("data", []):
                log_info(f"Stream found: {stream.get('user_name')} is live with {stream.get('viewer_count')} viewers.")
        except Exception as e:
            log_error(f"Error fetching streams: {e}", exc_info=True)

    def load_modules(self):
        for cog in COGS:
            try:
                log_info(f"Attempting to load extension: {cog}")
                self.load_module(cog)
                log_info(f"Loaded extension: {cog}")
                if hasattr(self.get_cog(cog.split(".")[-1]), "initialize"):
                    task = asyncio.create_task(self.get_cog(cog.split(".")[-1]).initialize())
                    self.cog_tasks.append(task)
            except Exception as e:
                log_error(f"Failed to load extension {cog}: {e}")

    async def join_channels(self):
        try:
            log_info(f"Attempting to join channels: {self.initial_channels}")
            await self._connection.join_channels(self.initial_channels)
            log_info(f"Successfully joined channels: {self.initial_channels}")
        except Exception as e:
            log_error(f"Failed to join channels: {e}")

    @commands.command(name="listcommands")
    async def list_commands(self, ctx: commands.Context):
        command_list = [cmd.name for cmd in self.commands.values()]
        await ctx.send(f"Available commands: {', '.join(command_list)}")

    async def event_error(self, error: Exception, data: str = None):
        """
        Handles errors in the bot's event loop.
        """
        log_error(f"Error in event loop: {error}")
        log_error(f"Error traceback: {error.__traceback__}")
        if data:
            log_error(f"Error data: {data}")

    async def check_token_regularly(self):
        while not self._closing.is_set():
            await asyncio.sleep(3600)  # Check every hour
            try:
                await self.twitch_api.ensure_token_valid()
                # Test the token with a simple API call
                user_info = await self.twitch_api.get_users([self.nick])
                if not user_info:
                    raise Exception("API call failed after token refresh")
                self.token = self.twitch_api.oauth_token  # Update the bot's token
            except Exception as e:
                log_error(f"Token validation failed: {e}")
                # Force a token refresh
                self.twitch_api.token_expiry = None
                await self.twitch_api.ensure_token_valid()
                self.token = self.twitch_api.oauth_token  # Update the bot's token

    async def handle_api_failure(self):
        log_warning("Entering reduced functionality mode due to API issues")
        # Disable features that require API calls
        for cog in self.cogs.values():
            if hasattr(cog, "disable_api_features"):
                cog.disable_api_features()
        # Notify channels about the issue
        for channel in self.connected_channels:
            await channel.send(
                "Bot is currently operating with reduced functionality due to API issues. Some features may be unavailable."
            )

    async def check_bot_state(self):
        while not self._closing.is_set():
            await asyncio.sleep(300)  # Check every 5 minutes
            if not self.token or not self._http.token:
                log_warning("Inconsistent token state detected. Refreshing token.")
                await self.twitch_api.ensure_token_valid()
                self.token = self.twitch_api.oauth_token
                self._http.token = self.token
            # Add other state checks as needed


async def main():
    bot = TwitchBot()
    try:
        await bot.start()
    except KeyboardInterrupt:
        log_info("Received keyboard interrupt. Shutting down...")
    except Exception as e:
        log_error(f"An unexpected error occurred: {e}")
        log_error(f"Error traceback: {e.__traceback__}")
    finally:
        await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
