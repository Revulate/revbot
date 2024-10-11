# cogs/admin.py

import os
from twitchio.ext import commands
from dotenv import load_dotenv

load_dotenv()


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.broadcaster_user_id = os.getenv("BROADCASTER_USER_ID")

    def is_admin(self, ctx):
        return str(ctx.author.id) == self.broadcaster_user_id

    @commands.command(name="load")
    async def load_cog(self, ctx: commands.Context, *, cog: str):
        if not self.is_admin(ctx):
            await ctx.send(f"@{ctx.author.name}, you don't have permission to use this command.")
            return
        try:
            self.bot.load_module(f"cogs.{cog}")
            await ctx.send(f"@{ctx.author.name}, successfully loaded cog '{cog}'.")
        except Exception as e:
            await ctx.send(f"@{ctx.author.name}, failed to load cog '{cog}': {str(e)}")

    @commands.command(name="unload")
    async def unload_cog(self, ctx: commands.Context, *, cog: str):
        if not self.is_admin(ctx):
            await ctx.send(f"@{ctx.author.name}, you don't have permission to use this command.")
            return
        try:
            self.bot.unload_module(f"cogs.{cog}")
            await ctx.send(f"@{ctx.author.name}, successfully unloaded cog '{cog}'.")
        except Exception as e:
            await ctx.send(f"@{ctx.author.name}, failed to unload cog '{cog}': {str(e)}")

    @commands.command(name="reload")
    async def reload_cog(self, ctx: commands.Context, *, cog: str):
        if not self.is_admin(ctx):
            await ctx.send(f"@{ctx.author.name}, you don't have permission to use this command.")
            return
        try:
            self.bot.reload_module(f"cogs.{cog}")
            await ctx.send(f"@{ctx.author.name}, successfully reloaded cog '{cog}'.")
        except Exception as e:
            await ctx.send(f"@{ctx.author.name}, failed to reload cog '{cog}': {str(e)}")

    @commands.command(name="reloadall")
    async def reload_all_cogs(self, ctx: commands.Context):
        if not self.is_admin(ctx):
            await ctx.send(f"@{ctx.author.name}, you don't have permission to use this command.")
            return

        cogs_dir = "cogs"
        cogs = [f[:-3] for f in os.listdir(cogs_dir) if f.endswith(".py") and not f.startswith("__")]

        failed_cogs = []
        for cog in cogs:
            try:
                self.bot.reload_module(f"cogs.{cog}")
            except Exception as e:
                failed_cogs.append(f"{cog}: {str(e)}")

        if failed_cogs:
            await ctx.send(f"@{ctx.author.name}, failed to reload some cogs: {', '.join(failed_cogs)}")
        else:
            await ctx.send(f"@{ctx.author.name}, successfully reloaded all cogs.")

    @commands.command(name="listcogs")
    async def list_cogs(self, ctx: commands.Context):
        if not self.is_admin(ctx):
            await ctx.send(f"@{ctx.author.name}, you don't have permission to use this command.")
            return

        cogs_dir = "cogs"
        cogs = [f[:-3] for f in os.listdir(cogs_dir) if f.endswith(".py") and not f.startswith("__")]
        await ctx.send(f"@{ctx.author.name}, available cogs: {', '.join(cogs)}")


def prepare(bot):
    bot.add_cog(Admin(bot))
