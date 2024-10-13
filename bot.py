import os
import asyncio
import random
from twitchio.ext import commands
from twitchio import AuthenticationError
from dotenv import load_dotenv
from logger import logger
from utils import CustomContext
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
    "cogs.dvp",  # Make sure this line is included
]


class TwitchBot(commands.Bot):
    def __init__(self):
        self.logger = logger

        # Use environment variables
        token = os.getenv("ACCESS_TOKEN")
        client_id = os.getenv("TWITCH_CLIENT_ID")
        client_secret = os.getenv("TWITCH_CLIENT_SECRET")
        refresh_token = os.getenv("REFRESH_TOKEN")
        nick = os.getenv("BOT_NICK")
        prefix = os.getenv("COMMAND_PREFIX", "#")
        channels = os.getenv("TWITCH_CHANNELS", "").split(",")

        # Check for missing critical environment variables
        self._check_env_variables()

        super().__init__(
            token=token,
            client_id=client_id,
            nick=nick,
            prefix=prefix,
            initial_channels=[channel.strip() for channel in channels if channel.strip()],
        )
        self.client_secret = client_secret
        self.broadcaster_user_id = os.getenv("BROADCASTER_USER_ID")
        self.bot_user_id = None
        self.context_class = CustomContext

        # Initialize TwitchAPI
        self.twitch_api = TwitchAPI(client_id, client_secret, token, refresh_token)
        self.twitch_api.save_tokens()  # Explicitly save tokens after initialization
        self.logger.info("TwitchAPI instance created and tokens saved")

    def _check_env_variables(self):
        """Check for missing critical environment variables."""
        required_vars = ["ACCESS_TOKEN", "TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET", "BOT_NICK", "REFRESH_TOKEN"]
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            error_msg = f"The following environment variables are missing: {', '.join(missing_vars)}"
            self.logger.error(error_msg)
            raise ValueError(error_msg)

    async def setup_auth(self):
        """Set up authentication if needed."""
        if not self.twitch_api.oauth_token or not self.twitch_api.refresh_token:
            flow_id, auth_url = await self.twitch_api.create_auth_flow(
                "YourAppName", ["chat:read", "chat:edit", "channel:moderate", "whispers:read", "whispers:edit"]
            )
            if flow_id and auth_url:
                print(f"Please visit this URL to authorize the application: {auth_url}")
                print("Waiting for authorization...")

                while True:
                    if await self.twitch_api.check_auth_status(flow_id):
                        print("Authorization successful!")
                        break
                    await asyncio.sleep(5)
            else:
                raise ValueError("Failed to create authorization flow.")

    async def event_ready(self):
        self.logger.info(f"Logged in as | {self.nick}")
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


def run(self):
    """Run the bot with authentication setup."""
    self.loop.run_until_complete(self.setup_auth())
    super().run()


def main():
    try:
        bot = TwitchBot()
        bot.run()
    except ValueError as e:
        logger.error(f"Bot initialization failed: {e}")
    except AuthenticationError as e:
        logger.error(f"Authentication Error: {e}. Please check your ACCESS_TOKEN.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)


if __name__ == "__main__":
    main()
