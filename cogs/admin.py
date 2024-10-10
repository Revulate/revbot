# cogs/admin.py

import os
import time
import psutil
from datetime import timedelta  # Ensure this import is present
from twitchio.ext import commands
from bot import COGS
from logger import setup_logger  # Import the centralized logger

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()
        # Get the broadcaster user ID from environment variables
        self.broadcaster_user_id = os.getenv('BROADCASTER_USER_ID')
        if self.broadcaster_user_id is None:
            print("Warning: BROADCASTER_USER_ID is not set in environment variables.")
        
        # Initialize the logger
        self.logger = setup_logger('twitch_bot.cogs.admin')  # Add this line

    def is_owner(self, ctx: commands.Context):
        # Check if the message author is the broadcaster
        return str(ctx.author.id) == str(self.broadcaster_user_id)

    @commands.command(name='load')
    async def load_cog(self, ctx: commands.Context, *, cog: str):
        """
        Loads a cog.
        Usage: #load cogname
        """
        if not self.is_owner(ctx):
            await ctx.send(f"@{ctx.author.name}, you do not have permission to use this command.")
            return
        try:
            module_name = f"cogs.{cog}" if not cog.startswith("cogs.") else cog
            self.bot.load_module(module_name)
            await ctx.send(f"@{ctx.author.name}, successfully loaded cog '{cog}'.")
            self.logger.info(f"Successfully loaded cog '{cog}'.")
        except Exception as e:
            await ctx.send(f"@{ctx.author.name}, failed to load cog '{cog}': {e}")
            self.logger.error(f"Failed to load cog '{cog}': {e}", exc_info=True)

    @commands.command(name='unload')
    async def unload_cog(self, ctx: commands.Context, *, cog: str):
        """
        Unloads a cog.
        Usage: #unload cogname
        """
        if not self.is_owner(ctx):
            await ctx.send(f"@{ctx.author.name}, you do not have permission to use this command.")
            return
        try:
            module_name = f"cogs.{cog}" if not cog.startswith("cogs.") else cog
            self.bot.unload_module(module_name)
            await ctx.send(f"@{ctx.author.name}, successfully unloaded cog '{cog}'.")
            self.logger.info(f"Successfully unloaded cog '{cog}'.")
        except Exception as e:
            await ctx.send(f"@{ctx.author.name}, failed to unload cog '{cog}': {e}")
            self.logger.error(f"Failed to unload cog '{cog}': {e}", exc_info=True)

    @commands.command(name='reload')
    async def reload_cog(self, ctx: commands.Context, *, cog: str):
        """
        Reloads a cog.
        Usage: #reload cogname
        """
        if not self.is_owner(ctx):
            await ctx.send(f"@{ctx.author.name}, you do not have permission to use this command.")
            return
        try:
            module_name = f"cogs.{cog}" if not cog.startswith("cogs.") else cog
            self.bot.reload_module(module_name)
            await ctx.send(f"@{ctx.author.name}, successfully reloaded cog '{cog}'.")
            self.logger.info(f"Successfully reloaded cog '{cog}'.")
        except Exception as e:
            await ctx.send(f"@{ctx.author.name}, failed to reload cog '{cog}': {e}")
            self.logger.error(f"Failed to reload cog '{cog}': {e}", exc_info=True)

    @commands.command(name='reloadall')
    async def reload_all_cogs(self, ctx: commands.Context):
        """
        Reloads all cogs.
        Usage: #reloadall
        """
        if not self.is_owner(ctx):
            await ctx.send(f"@{ctx.author.name}, you do not have permission to use this command.")
            return
        failed = []
        for extension in COGS:
            try:
                self.bot.reload_module(extension)
                self.logger.info(f"Successfully reloaded cog '{extension}'.")
            except Exception as e:
                failed.append(f'{extension}: {e}')
                self.logger.error(f"Failed to reload cog '{extension}': {e}", exc_info=True)
        if failed:
            await ctx.send(f"@{ctx.author.name}, failed to reload some cogs: {', '.join(failed)}")
        else:
            await ctx.send(f"@{ctx.author.name}, successfully reloaded all cogs.")

    @commands.command(name='uptime')
    async def uptime(self, ctx: commands.Context):
        """
        Shows the bot's uptime and memory usage.
        Usage: #uptime
        """
        now = time.time()
        delta = timedelta(seconds=now - self.start_time)
        uptime_str = str(delta).split('.')[0]  # Remove microseconds
        # Get memory usage
        process = psutil.Process()
        mem_info = process.memory_info()
        mem_usage_mb = mem_info.rss / 1024 / 1024  # Convert bytes to MB

        await ctx.send(f"@{ctx.author.name}, I have been running for {uptime_str}. Memory usage: {mem_usage_mb:.2f} MB")
        self.logger.info(f"Uptime requested by {ctx.author.name}: {uptime_str}, Memory usage: {mem_usage_mb:.2f} MB")

    @commands.command(name='echo')
    async def echo_command(self, ctx: commands.Context, *, message: str = None):
        """
        Echoes the message provided by the bot owner.
        Usage:
        - #echo Your message here
        - #echo #channelname Your message here
        """
        if not self.is_owner(ctx):
            await ctx.send(f"@{ctx.author.name}, you do not have permission to use this command.")
            self.logger.warning(f"Unauthorized echo attempt by {ctx.author.name}.")
            return

        if not message:
            await ctx.send(f"@{ctx.author.name}, please provide a message to echo.")
            self.logger.warning(f"Echo command invoked by {ctx.author.name} without a message.")
            return

        # Check if a channel is specified at the start of the message
        if message.startswith('#'):
            parts = message.split(' ', 1)
            if len(parts) < 2:
                await ctx.send(f"@{ctx.author.name}, please provide a message to echo after the channel.")
                self.logger.warning(f"Echo command invoked by {ctx.author.name} with channel but no message.")
                return
            channel_name = parts[0][1:].lower()  # Remove '#' and convert to lowercase
            message_to_send = parts[1]

            # Check if the bot is connected to the specified channel
            connected_channel_names = [channel.name.lower() for channel in self.bot.connected_channels]
            if channel_name in connected_channel_names:
                # Retrieve the channel object
                target_channel = self.bot.get_channel(channel_name)
                if target_channel:
                    self.logger.info(f"Echo command used by {ctx.author.name} in #{channel_name}: {message_to_send}")
                    try:
                        await target_channel.send(message_to_send)
                        await ctx.send(f"@{ctx.author.name}, message successfully sent to #{channel_name}.")
                        self.logger.info(f"Message successfully sent to #{channel_name} by {ctx.author.name}.")
                    except Exception as e:
                        self.logger.error(f"Error sending echo message to #{channel_name}: {e}", exc_info=True)
                        await ctx.send(f"@{ctx.author.name}, an error occurred while sending the message to #{channel_name}.")
                else:
                    await ctx.send(f"@{ctx.author.name}, could not find channel #{channel_name}.")
                    self.logger.error(f"Channel object for #{channel_name} not found.")
            else:
                await ctx.send(f"@{ctx.author.name}, I am not connected to channel #{channel_name}.")
                self.logger.warning(f"Echo command attempted to send to disconnected channel #{channel_name} by {ctx.author.name}.")
        else:
            # No channel specified, send the message in the current channel
            self.logger.info(f"Echo command used by {ctx.author.name} in #{ctx.channel.name}: {message}")
            try:
                await ctx.send(message)
                self.logger.info(f"Message successfully sent in #{ctx.channel.name} by {ctx.author.name}.")
            except Exception as e:
                self.logger.error(f"Error sending echo message in #{ctx.channel.name}: {e}", exc_info=True)
                await ctx.send(f"@{ctx.author.name}, an error occurred while sending the message.")

def prepare(bot):
    bot.add_cog(Admin(bot))