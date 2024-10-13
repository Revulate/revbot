import time
import psutil
from twitchio.ext import commands
from datetime import timedelta


class Uptime(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()

    @commands.command(name="uptime")
    async def uptime_command(self, ctx: commands.Context):
        """Display bot uptime and memory usage."""
        # Calculate uptime
        current_time = time.time()
        uptime_seconds = int(current_time - self.start_time)
        uptime = str(timedelta(seconds=uptime_seconds))

        # Get memory usage
        process = psutil.Process()
        memory_info = process.memory_info()
        ram_usage = memory_info.rss / (1024 * 1024)  # Convert to MB

        # Get storage usage
        storage = psutil.disk_usage("/")
        storage_usage = storage.used / (1024 * 1024 * 1024)  # Convert to GB

        # Prepare and send the response
        response = (
            f"@{ctx.author.name}, I've been running for {uptime}. "
            f"Currently using {ram_usage:.2f} MB of RAM and {storage_usage:.2f} GB of storage."
        )
        await ctx.send(response)


def prepare(bot):
    bot.add_cog(Uptime(bot))
