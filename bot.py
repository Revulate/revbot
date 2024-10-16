import os
import asyncio
import datetime
from twitchio.ext import commands
from dotenv import load_dotenv
from logger import setup_logger
from utils import setup_database, get_database_connection
from twitch_helix_client import TwitchAPI

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
        self.logger = setup_logger("twitch_bot")

        # Use environment variables
        self.token = os.getenv("ACCESS_TOKEN")
        self.client_id = os.getenv("TWITCH_CLIENT_ID")
        self.client_secret = os.getenv("TWITCH_CLIENT_SECRET")
        self.refresh_token = os.getenv("REFRESH_TOKEN")
        nick = os.getenv("BOT_NICK")
        prefix = os.getenv("COMMAND_PREFIX", "#")
        channels = os.getenv("TWITCH_CHANNELS", "").split(",")

        # Check for missing critical environment variables
        self._check_env_variables()

        # Set initial_channels as an instance variable
        self.initial_channels = [channel.strip() for channel in channels if isinstance(channel.strip(), str)]

        super().__init__(
            token=self.token,
            client_id=self.client_id,
            nick=nick,
            prefix=prefix,
            initial_channels=self.initial_channels,
        )
        self.broadcaster_user_id = os.getenv("BROADCASTER_USER_ID")
        self.bot_user_id = None
        self.http_session = None
        self.token_check_task = None

        # Initialize TwitchAPI
        redirect_uri = os.getenv("TWITCH_REDIRECT_URI", "http://localhost:3000")
        self.twitch_api = TwitchAPI(self.client_id, self.client_secret, redirect_uri)
        self.twitch_api.oauth_token = self.token
        self.twitch_api.refresh_token = self.refresh_token
        self.logger.info("TwitchAPI instance created and tokens saved")

        self._connection_retries = 0
        self._max_retries = 5
        self._closing = asyncio.Event()
        self.cog_tasks = []

    async def event_ready(self):
        self.logger.info(f"Logged in as | {self.nick}")
        await self.ensure_valid_token()
        await self.fetch_user_id()
        await self.fetch_example_streams()
        await self.join_channels()
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

    async def start(self):
        await self.ensure_valid_token()
        while self._connection_retries < self._max_retries:
            try:
                await super().start()
                break
            except Exception as e:
                self._connection_retries += 1
                self.logger.error(f"Connection attempt {self._connection_retries} failed: {e}")
                if self._connection_retries < self._max_retries:
                    await asyncio.sleep(5 * self._connection_retries)  # Exponential backoff
                else:
                    self.logger.error("Max retries reached. Unable to connect.")
                    raise

    async def close(self):
        self._closing.set()
        try:
            for task in self.cog_tasks:
                task.cancel()
            await asyncio.gather(*self.cog_tasks, return_exceptions=True)

            if self._connection and hasattr(self._connection, "_close"):
                await self._connection._close()
            if hasattr(self, "_http") and self._http:
                await self._http.close()
            if self.http_session:
                await self.http_session.close()
            if self.twitch_api:
                await self.twitch_api.close()
        except Exception as e:
            self.logger.error(f"Error during close: {e}")
        finally:
            await super().close()

    async def _close_cogs(self):
        for name, cog in self.cogs.items():
            if hasattr(cog, "cog_unload") and asyncio.iscoroutinefunction(cog.cog_unload):
                try:
                    await cog.cog_unload()
                except Exception as e:
                    self.logger.error(f"Error unloading cog {name}: {e}")

    async def ensure_valid_token(self):
        if not self.twitch_api.token_expiry or self.twitch_api.token_expiry <= datetime.datetime.now():
            self.logger.info("Token expired or close to expiry. Refreshing...")
            try:
                success = await asyncio.wait_for(self.twitch_api.refresh_oauth_token(), timeout=10)
                if success:
                    self.token = self.twitch_api.oauth_token
                    self.refresh_token = self.twitch_api.refresh_token
                    self._update_env_file()
                    load_dotenv(override=True)
                    self.logger.info("Access token refreshed successfully")
                else:
                    self.logger.error("Failed to refresh access token")
            except asyncio.TimeoutError:
                self.logger.error("Token refresh timed out")
            except Exception as e:
                self.logger.error(f"Error during token refresh: {e}")
        return True

    def _update_env_file(self):
        env_path = ".env"
        with open(env_path, "r") as file:
            lines = file.readlines()

        with open(env_path, "w") as file:
            for line in lines:
                if line.startswith("ACCESS_TOKEN="):
                    file.write(f"ACCESS_TOKEN={self.token}\n")
                elif line.startswith("REFRESH_TOKEN="):
                    file.write(f"REFRESH_TOKEN={self.refresh_token}\n")
                else:
                    file.write(line)

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
                delay = base_delay * (2 ** (attempt - 1))
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
                if hasattr(self.get_cog(cog.split(".")[-1]), "initialize"):
                    task = asyncio.create_task(self.get_cog(cog.split(".")[-1]).initialize())
                    self.cog_tasks.append(task)
            except Exception as e:
                self.logger.error(f"Failed to load extension {cog}: {e}")

    async def join_channels(self):
        for channel in self.initial_channels:
            try:
                self.logger.info(f"Attempting to join channel: {channel}")
                await self._connection.join_channels([channel])
                self.logger.info(f"Successfully joined channel: {channel}")
            except Exception as e:
                self.logger.error(f"Failed to join channel {channel}: {e}")

    @commands.command(name="listcommands")
    async def list_commands(self, ctx: commands.Context):
        command_list = [cmd.name for cmd in self.commands.values()]
        await ctx.send(f"Available commands: {', '.join(command_list)}")

    async def event_error(self, error: Exception, data: str = None):
        """
        Handles errors in the bot's event loop.
        """
        self.logger.error(f"Error in event loop: {error}")
        self.logger.error(f"Error traceback: {error.__traceback__}")
        if data:
            self.logger.error(f"Error data: {data}")

    async def check_token_regularly(self):
        while not self._closing.is_set():
            await asyncio.sleep(3600)  # Check every hour
            await self.ensure_valid_token()


async def main():
    bot = TwitchBot()
    try:
        await bot.start()
    except KeyboardInterrupt:
        bot.logger.info("Received keyboard interrupt. Shutting down...")
    except Exception as e:
        bot.logger.error(f"An unexpected error occurred: {e}")
        bot.logger.error(f"Error traceback: {e.__traceback__}")
    finally:
        await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
