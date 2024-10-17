import time
import psutil
import os
from twitchio.ext import commands
from datetime import timedelta
from logger import log_info, log_error


class Uptime(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()
        self.bot_folder = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def get_folder_size(self, folder):
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(folder):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                total_size += os.path.getsize(fp)
        return total_size

    @commands.command(name="uptime")
    async def uptime_command(self, ctx: commands.Context):
        try:
            current_time = time.time()
            uptime_seconds = int(current_time - self.start_time)
            uptime = str(timedelta(seconds=uptime_seconds))

            process = psutil.Process()
            memory_info = process.memory_info()
            ram_usage = memory_info.rss / (1024 * 1024)  # Convert to MB

            bot_storage = self.get_folder_size(self.bot_folder) / (1024 * 1024 * 1024)  # Convert to GB

            response = (
                f"@{ctx.author.name}, I've been running for {uptime}. "
                f"Currently using {ram_usage:.2f} MB of RAM and {bot_storage:.2f} GB of bot storage."
            )
            await ctx.send(response)
            log_info(f"Uptime command executed by {ctx.author.name}")
        except Exception as e:
            log_error(f"Error in uptime command: {e}")
            await ctx.send(f"@{ctx.author.name}, an error occurred while processing the uptime command.")


def prepare(bot):
    bot.add_cog(Uptime(bot))
