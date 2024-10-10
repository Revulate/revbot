import os
import logging
from twitchio.ext import commands
from dotenv import load_dotenv
from logging.handlers import RotatingFileHandler
from twitch_helix_client import TwitchAPI  # Placeholder for Helix API integration
import importlib
import glob

# Load environment variables from .env file
load_dotenv()

# Set up logging with rotation
log_handler = RotatingFileHandler("logs/bot.log", maxBytes=5*1024*1024, backupCount=3)
logging.basicConfig(level=logging.INFO, handlers=[log_handler])
logger = logging.getLogger(__name__)

class Bot(commands.Bot):

    def __init__(self):
        # Initialize the bot with access token, command prefix, and initial channels
        super().__init__(
            token=os.getenv('ACCESS_TOKEN'),
            prefix=os.getenv('COMMAND_PREFIX', '#'),
            initial_channels=[channel.strip() for channel in os.getenv('TWITCH_CHANNELS', 'your_channel_name').split(',')]
        )
        self.twitch_api = TwitchAPI()  # Placeholder for Twitch Helix API client

    async def event_ready(self):
        # Called when the bot is ready to start interacting
        logger.info(f'Logged in as | {self.nick}')
        logger.info(f'User id is | {self.user_id}')

    async def event_message(self, message):
        # Process incoming messages and handle commands
        if message.echo:
            return

        logger.info(f"Message from {message.author.name}: {message.content}")
        await self.handle_commands(message)

    @commands.command()
    async def hello(self, ctx: commands.Context):
        # Command that sends a greeting message
        await ctx.send(f'Hello {ctx.author.name}!')

    @commands.command()
    async def preview(self, ctx: commands.Context, channel: str):
        # Placeholder command to preview a channel using Helix API
        try:
            stream_info = await self.twitch_api.get_stream(channel)
            if stream_info:
                await ctx.send(f"{channel} is live with {stream_info['viewer_count']} viewers: {stream_info['title']}")
            else:
                await ctx.send(f"{channel} is not live right now.")
        except Exception as e:
            logger.error(f"Error fetching stream info for {channel}: {e}")
            await ctx.send(f"Could not retrieve stream information for {channel}.")

    @commands.command()
    async def reloadall(self, ctx: commands.Context):
        # Command to reload all cogs dynamically
        try:
            self.unload_all_cogs()
            self.load_cogs()
            await ctx.send("All cogs reloaded successfully!")
            logger.info("All cogs reloaded successfully.")
        except Exception as e:
            logger.error(f"Failed to reload cogs: {e}")
            await ctx.send(f"Failed to reload cogs: {e}")

    def load_cogs(self):
        # Load all cogs dynamically from the cogs/ directory
        cog_files = glob.glob("cogs/*.py")
        for cog in cog_files:
            cog_name = cog.replace('/', '.').replace('\\', '.').replace('.py', '')
            try:
                self.load_module(cog_name)
                logger.info(f"Loaded cog: {cog_name}")
            except Exception as e:
                logger.error(f"Failed to load cog {cog_name}: {e}")

    def unload_all_cogs(self):
        # Unload all currently loaded cogs
        for ext in list(self.cogs):
            try:
                self.unload_module(ext)
                logger.info(f"Unloaded cog: {ext}")
            except Exception as e:
                logger.error(f"Failed to unload cog {ext}: {e}")

if __name__ == "__main__":
    bot = Bot()
    bot.load_cogs()
    bot.run()