# cogs/admin.py

import os
import time
import psutil
from datetime import timedelta  # Ensure this import is present
from twitchio.ext import commands
from cogs_list import COGS  # Import the centralized cogs list

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()
        # Get the broadcaster user ID from environment variables
        self.broadcaster_user_id = os.getenv('BROADCASTER_USER_ID')
        if self.broadcaster_user_id is None:
            print("Warning: BROADCASTER_USER_ID is not set in environment variables.")

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
        except Exception as e:
            await ctx.send(f"@{ctx.author.name}, failed to load cog '{cog}': {e}")

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
        except Exception as e:
            await ctx.send(f"@{ctx.author.name}, failed to unload cog '{cog}': {e}")

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
        except Exception as e:
            await ctx.send(f"@{ctx.author.name}, failed to reload cog '{cog}': {e}")

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
            except Exception as e:
                failed.append(f'{extension}: {e}')
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

def prepare(bot):
    bot.add_cog(Admin(bot))
