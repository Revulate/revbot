import os
import logging
import sys
from twitchio.ext import commands
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class TwitchBot(commands.Bot):
    def __init__(self):
        # Retrieve environment variables
        token = os.getenv('TWITCH_OAUTH_TOKEN')
        prefix = os.getenv('COMMAND_PREFIX', '!')
        channels = os.getenv('TWITCH_CHANNELS', '')

        # Check if essential environment variables are set
        missing_vars = []
        if not token:
            missing_vars.append('TWITCH_OAUTH_TOKEN')
        if not channels:
            missing_vars.append('TWITCH_CHANNELS')
        if missing_vars:
            for var in missing_vars:
                print(f"ERROR: Missing environment variable '{var}' in .env file.")
            sys.exit(1)  # Exit the program

        super().__init__(
            token=token,
            prefix=prefix,
            initial_channels=[channel.strip() for channel in channels.split(',') if channel.strip()]
        )
        self.logger = self.setup_logger()

    def setup_logger(self):
        logger = logging.getLogger('twitch_bot')
        logger.setLevel(logging.DEBUG)  # Set to DEBUG for verbose logging

        # Create handlers with utf-8 encoding
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)  # Capture DEBUG and above in console
        console_formatter = logging.Formatter('[%(asctime)s] %(levelname)s:%(name)s: %(message)s')
        console_handler.setFormatter(console_formatter)

        file_handler = logging.FileHandler('bot.log', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)  # Capture DEBUG and above in log file
        file_formatter = logging.Formatter('[%(asctime)s] %(levelname)s:%(name)s: %(message)s')
        file_handler.setFormatter(file_formatter)

        # Add handlers to the logger
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

        return logger

    async def event_ready(self):
        self.logger.info(f'Logged in as | {self.nick}')
        
        # Fetch user data to obtain user ID
        try:
            users = await self.fetch_users([self.nick])
            if users:
                user_id = users[0].id
                self.logger.info(f'User ID is | {user_id}')
            else:
                self.logger.error("Failed to fetch user data.")
        except Exception as e:
            self.logger.error(f"Error fetching user data: {e}", exc_info=True)

        # Manually add cogs without using load_extension
        from cogs.gpt import Gpt
        self.add_cog(Gpt(self))
        self.logger.info("Added cog: Gpt")

        from cogs.roll import Roll
        self.add_cog(Roll(self))
        self.logger.info("Added cog: Roll")

        from cogs.rate import Rate
        self.add_cog(Rate(self))
        self.logger.info("Added cog: Rate")

    async def event_message(self, message):
        if message.echo:
            return
        
        # Log the channel, user, and message
        self.logger.debug(f"#{message.channel.name} - {message.author.name}: {message.content}")
        
        await self.handle_commands(message)


    async def event_command_error(self, context: commands.Context, error: Exception):
        if isinstance(error, commands.CommandNotFound):
            # Optionally, notify the user or silently ignore
            self.logger.warning(f"Command not found: {context.message.content}")
            return

        elif isinstance(error, commands.ArgumentParsingFailed):
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
    # Set the console code page to UTF-8 to handle Unicode characters
    os.system('chcp 65001 > nul')

    try:
        bot = TwitchBot()
        bot.run()
    except Exception as e:
        logging.getLogger('twitch_bot').error(f"Bot encountered an error: {e}", exc_info=True)
