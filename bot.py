# bot.py

import os
import sys
import logging
from twitchio.ext import commands
from dotenv import load_dotenv
from logger import setup_logger
from utils import CustomContext  # Adjust import path if necessary
from cogs_list import COGS  # Import the centralized cogs list

# Load environment variables from .env file
load_dotenv()

class TwitchBot(commands.Bot):
    def __init__(self):
        # Set up the logger
        self.logger = setup_logger()

        # Retrieve environment variables
        token = os.getenv('TWITCH_OAUTH_TOKEN')
        client_id = os.getenv('CLIENT_ID')
        nick = os.getenv('BOT_NICK')
        prefix = os.getenv('COMMAND_PREFIX', '#')  # Default prefix is '#'
        channels = os.getenv('TWITCH_CHANNELS', '')

        # Check if essential environment variables are set
        self.check_environment_variables(token, client_id, nick, channels)

        # Initialize the bot with token, client ID, nick, prefix, and channels
        super().__init__(
            token=token,
            client_id=client_id,
            nick=nick,
            prefix=prefix,
            initial_channels=[channel.strip() for channel in channels.split(',') if channel.strip()]
        )
        self.bot_user_id = None  # Initialize the attribute to store the bot's user ID

        # Set the custom context class
        self.context_class = CustomContext

        # Load cogs
        self.load_cogs()

    def check_environment_variables(self, token, client_id, nick, channels):
        """Check for missing environment variables and exit if any are missing."""
        missing_vars = []
        if not token:
            missing_vars.append('TWITCH_OAUTH_TOKEN')
        if not client_id:
            missing_vars.append('CLIENT_ID')
        if not nick:
            missing_vars.append('BOT_NICK')
        if not channels:
            missing_vars.append('TWITCH_CHANNELS')

        if missing_vars:
            for var in missing_vars:
                self.logger.error(f"Missing environment variable '{var}' in .env file.")
            sys.exit(1)  # Exit the program

    async def event_ready(self):
        self.logger.info(f'Logged in as | {self.nick}')
        await self.fetch_user_id()

    async def event_channel_joined(self, channel):
        self.logger.info(f"Joined channel: {channel.name}")

    async def fetch_user_id(self):
        """Fetch user data to obtain user ID."""
        try:
            users = await self.fetch_users(names=[self.nick])
            if users:
                user_id = users[0].id
                self.bot_user_id = user_id  # Store the bot's user ID
                self.logger.info(f'User ID is | {self.bot_user_id}')
            else:
                self.logger.error("Failed to fetch user data.")
        except Exception as e:
            self.logger.error(f"Error fetching user data: {e}", exc_info=True)

    def load_cogs(self):
        """Load all cogs as extensions."""
        for cog in COGS:
            try:
                self.load_module(cog)
                self.logger.info(f"Loaded extension: {cog}")
            except Exception as e:
                self.logger.error(f"Failed to load extension {cog}: {e}", exc_info=True)

    async def event_message(self, message):
        """Process incoming messages and handle commands."""
        if not message or not message.channel or not message.author:
            self.log_missing_data(message)
            return

        # Prevent the bot from responding to its own messages
        if self.bot_user_id and message.author.id == self.bot_user_id:
            self.logger.debug(f"Ignored message from bot itself: {message.content}")
            return

        self.logger.debug(f"Processing message from #{message.channel.name} - {message.author.name}: {message.content}")

        if message.echo:
            self.logger.debug(f"Ignored echo message: {message.content}")
            return

        try:
            await self.handle_commands(message)
        except Exception as e:
            self.logger.error(f"Error handling message: {e}", exc_info=True)

    def log_missing_data(self, message):
        """Log missing data in message."""
        self.logger.warning(
            f"Received a message with missing data. Content: {getattr(message, 'content', 'None')}, "
            f"Channel: {getattr(message.channel, 'name', 'None')}"
        )

    async def event_command_error(self, context: commands.Context, error: Exception):
        """Handle command errors."""
        if isinstance(error, commands.CommandNotFound):
            self.logger.warning(f"Command not found: {context.message.content}")
            return

        if isinstance(error, commands.ArgumentParsingFailed):
            await context.send(f"{error.message}")
        elif isinstance(error, commands.MissingRequiredArgument):
            await context.send(f"@{context.author.name}, you're missing a required argument for the command.")
        elif isinstance(error, commands.CheckFailure):
            await context.send(f"@{context.author.name}, you don't have permission to use that command.")
        elif isinstance(error, commands.CommandOnCooldown):
            await context.send(f"@{context.author.name}, this command is on cooldown. Please try again in {round(error.retry_after, 2)} seconds.")
        else:
            self.logger.error(f"Unhandled exception: {error}", exc_info=True)
            await context.send(f"@{context.author.name}, an unexpected error occurred. Please try again later.")

# Instantiate and run the bot
if __name__ == '__main__':
    # Ensure the console supports UTF-8 encoding (Windows specific)
    if os.name == 'nt':
        os.system('chcp 65001 > nul')  # Set the console code page to UTF-8

    try:
        bot = TwitchBot()
        bot.run()
    except Exception as e:
        logging.getLogger('twitch_bot').error(f"Bot encountered an error: {e}", exc_info=True)
