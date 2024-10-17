from dotenv import load_dotenv
from twitchio.ext import commands
from datetime import datetime, timezone
from utils import normalize_username
from logger import log_info, log_error, log_warning, log_debug

load_dotenv()


class User(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def format_enum(self, enum_value):
        if enum_value is None:
            return "None"
        return str(enum_value).split(".")[-1].capitalize()

    def format_account_age(self, created_at):
        now = datetime.now(timezone.utc)
        age = now - created_at
        years, remainder = divmod(age.days, 365)
        months, days = divmod(remainder, 30)

        age_parts = []
        if years > 0:
            age_parts.append(f"{years} year{'s' if years != 1 else ''}")
        if months > 0:
            age_parts.append(f"{months} month{'s' if months != 1 else ''}")
        if days > 0:
            age_parts.append(f"{days} day{'s' if days != 1 else ''}")

        age_str = ", ".join(age_parts)
        return f"{age_str} ago (Created on {created_at.strftime('%Y-%m-%d')})"

    async def get_ban_info(self, broadcaster_id, user_id):
        try:
            if hasattr(self.bot, "fetch_channel_bans"):
                bans = await self.bot.fetch_channel_bans(broadcaster_id, user_ids=[user_id])
                return bans[0] if bans else None
            else:
                log_warning("fetch_channel_bans method not available. Unable to fetch ban info.")
                return None
        except Exception as e:
            log_error(f"Error fetching ban info: {e}")
            return None

    @commands.command(name="user")
    async def user_command(self, ctx: commands.Context, username: str = None):
        if username:
            username = normalize_username(username)

        try:
            users = await self.bot.fetch_users(names=[username])
            if not users:
                await ctx.send(f"@{ctx.author.name}, no user found with the name '{username}'.")
                return

            user = users[0]
            account_age = self.format_account_age(user.created_at)

            broadcaster_name = ctx.channel.name
            broadcasters = await self.bot.fetch_users(names=[broadcaster_name])
            if not broadcasters:
                await ctx.send(f"@{ctx.author.name}, could not fetch broadcaster information.")
                return

            broadcaster = broadcasters[0]
            broadcaster_id = broadcaster.id

            ban_info = await self.get_ban_info(broadcaster_id, user.id)

            response = (
                f"@{ctx.author.name}, User info for {user.display_name} (twitch.tv/{user.name}): "
                f"ID: {user.id} | "
                f"Created: {account_age} | "
                f"Bio: {user.description[:100]}{'...' if len(user.description) > 100 else ''} | "
                f"Profile Picture: {user.profile_image}"
            )

            if ban_info:
                ban_type = "Banned" if ban_info.expires_at is None else "Timed out"
                expiry = (
                    f" until {ban_info.expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}" if ban_info.expires_at else ""
                )
                banned_by = ban_info.moderator.name if ban_info.moderator else "Unknown"

                response += (
                    f" | {ban_type} in this channel{expiry} | "
                    f"Reason: {ban_info.reason or 'No reason provided'} | "
                    f"Banned by: {banned_by}"
                )

            await ctx.send(response)
            log_info(f"User info sent for {username}")
        except Exception as e:
            log_error(f"Error fetching user info: {e}")
            await ctx.send(
                f"@{ctx.author.name}, an error occurred while fetching user information. Please try again later."
            )


def prepare(bot):
    bot.add_cog(User(bot))
