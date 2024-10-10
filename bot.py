# bot.py

import os
import sys
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from twitchio.ext import commands
from dotenv import load_dotenv
from logger import setup_logger
from utils import CustomContext  # Adjust import path if necessary
import configparser
import random

# Load environment variables from .env file
load_dotenv()

# Load config.ini file
config = configparser.ConfigParser()
config.read('config.ini')

# Set LOGDNA_INGESTION_KEY if it's defined in config.ini
if 'Logging' in config and 'LOGDNA_INGESTION_KEY' in config['Logging']:
    os.environ['LOGDNA_INGESTION_KEY'] = config['Logging']['LOGDNA_INGESTION_KEY']

# List of cogs
COGS = [
    'cogs.gpt',
    'cogs.roll',
    'cogs.rate',
    'cogs.afk',
    'cogs.preview',
    # 'cogs.react',
    'cogs.remind',
    'cogs.admin',
    'cogs.spc',
    'cogs.dnd'  # Add this line to include the DnD cog
]

class TwitchBot(commands.Bot):
    def __init__(self):
        # Set up the logger
        self.logger = setup_logger()

        # Load configuration
        config = self.load_config()
        token = config.get('Twitch', 'TWITCH_OAUTH_TOKEN')
        client_id = config.get('Twitch', 'CLIENT_ID')
        nick = config.get('Twitch', 'BOT_NICK')
        prefix = config.get('Twitch', 'COMMAND_PREFIX', fallback='#')  # Default prefix is '#'
        channels = config.get('Twitch', 'TWITCH_CHANNELS', fallback='')

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

    def load_config(self):
        """Load configuration from a centralized configuration file."""
        config = configparser.ConfigParser()
        config.read('config.ini')

        # Check for missing sections or options
        if 'Twitch' not in config:
            raise EnvironmentError("Missing 'Twitch' section in config.ini file.")
        required_keys = ['TWITCH_OAUTH_TOKEN', 'CLIENT_ID', 'BOT_NICK']
        missing_keys = [key for key in required_keys if key not in config['Twitch']]
        if missing_keys:
            raise EnvironmentError(f"Missing required keys in 'Twitch' section of config.ini: {', '.join(missing_keys)}")

        return config

    async def event_ready(self):
        self.logger.info(f'Logged in as | {self.nick}')
        await self.fetch_user_id()

    async def event_channel_joined(self, channel):
        self.logger.info(f"Joined channel: {channel.name}")

    async def fetch_user_id(self):
        """Fetch user data to obtain user ID with retry mechanism for transient failures using exponential backoff."""
        retries = 3
        base_delay = 5  # Initial delay in seconds
        for attempt in range(1, retries + 1):
            try:
                users = await self.fetch_users(names=[self.nick])
                if users:
                    user_id = users[0].id
                    self.bot_user_id = user_id  # Store the bot's user ID
                    self.logger.info(f'User ID is | {self.bot_user_id}')
                    return
                else:
                    self.logger.error("Failed to fetch user data.")
            except Exception as e:
                self.logger.error(f"Attempt {attempt} - Error fetching user data: {e}", exc_info=True)

            if attempt < retries:
                delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1)  # Exponential backoff with jitter
                self.logger.info(f"Retrying to fetch user data in {delay:.2f} seconds...")
                await asyncio.sleep(delay)

        self.logger.error("Exceeded maximum retries to fetch user data.")

    def load_cogs(self):
        """Load all cogs as modules."""
        for cog in COGS:
            try:
                self.load_module(cog)
                cog_name = cog.split('.')[-1].capitalize()
                self.logger.info(f"Loaded extension: {cog_name}")
            except Exception as e:
                self.logger.error(f"Failed to load extension {cog}: {e}", exc_info=True)

    async def event_message(self, message):
        """Process incoming messages and handle commands."""
        if not self._validate_message(message):
            return

        if self._is_bot_message(message):
            return

        self._log_message_processing(message)

        try:
            await self.handle_commands(message)
        except commands.CommandNotFound as e:
            self.logger.warning(f"Command not found: {message.content}")
        except commands.ArgumentParsingFailed as e:
            self.logger.error(f"Argument parsing failed: {message.content}", exc_info=True)
        except commands.MissingRequiredArgument as e:
            self.logger.error(f"Missing required argument: {message.content}", exc_info=True)
            await message.channel.send(f"@{message.author.name}, you're missing a required argument for the command.")
        except commands.CheckFailure as e:
            self.logger.error(f"Check failed for command: {message.content}", exc_info=True)
            await message.channel.send(f"@{message.author.name}, you don't have permission to use that command.")
        except commands.CommandOnCooldown as e:
            self.logger.warning(f"Command on cooldown: {message.content}")
            await message.channel.send(f"@{message.author.name}, this command is on cooldown. Please try again in {round(e.retry_after, 2)} seconds.")
        except Exception as e:
            self.logger.error(f"Error handling message: {e}", exc_info=True)
            await message.channel.send(f"@{message.author.name}, an unexpected error occurred while processing your command.")

    def _validate_message(self, message):
        """Validate the incoming message to ensure it has necessary attributes."""
        if not message or not message.channel or not message.author:
            self.log_missing_data(message)
            return False
        return True

    def _is_bot_message(self, message):
        """Check if the message is from the bot itself or an echo message."""
        if self.bot_user_id and message.author.id == self.bot_user_id:
            self.logger.debug(f"Ignored message from bot itself: {message.content}")
            return True
        if message.echo:
            self.logger.debug(f"Ignored echo message: {message.content}")
            return True
        return False

    def _log_message_processing(self, message):
        """Log details about the message being processed."""
        self.logger.debug(f"Processing message from #{message.channel.name} - {message.author.name}: {message.content}")

    def log_missing_data(self, message):
        """Log missing data in message."""
        content = getattr(message, 'content', 'None')
        channel = getattr(message.channel, 'name', 'None')
        author = getattr(message.author, 'name', 'None')
        self.logger.warning(
            f"Received a message with missing data. Content: {content}, Author: {author}, Channel: {channel}"
        )

    async def event_command_error(self, context: commands.Context, error: Exception):
        """Handle command errors."""
        if isinstance(error, commands.CommandNotFound):
            self.logger.warning(f"Command not found: {context.message.content}")
            return

        if isinstance(error, commands.ArgumentParsingFailed):
            self.logger.error(f"Argument parsing failed: {context.message.content}", exc_info=True)
            await context.send(f"{str(error)}")
        elif isinstance(error, commands.MissingRequiredArgument):
            self.logger.error(f"Missing required argument: {context.message.content}", exc_info=True)
            await context.send(f"@{context.author.name}, you're missing a required argument for the command.")
        elif isinstance(error, commands.CheckFailure):
            self.logger.error(f"Check failed for command: {context.message.content}", exc_info=True)
            await context.send(f"@{context.author.name}, you don't have permission to use that command.")
        elif isinstance(error, commands.CommandOnCooldown):
            self.logger.warning(f"Command on cooldown: {context.message.content}")
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