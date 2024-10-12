import os
from dotenv import load_dotenv
from twitchio.ext import commands
from datetime import datetime, timezone

load_dotenv()


class User(commands.Cog):
    """Cog for displaying Twitch user information."""

    def __init__(self, bot):
        self.bot = bot

    def format_enum(self, enum_value):
        """Format enum value to a readable string."""
        if enum_value is None:
            return "None"
        return str(enum_value).split(".")[-1].capitalize()

    def format_account_age(self, created_at):
        """Format account age to include years, months, and the exact creation date."""
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

    async def get_ban_info(self, channel_id, user_id):
        """Fetch ban information for a user in a specific channel."""
        try:
            bans = await self.bot.fetch_channel_bans(channel_id, user_ids=[user_id])
            return bans[0] if bans else None
        except Exception as e:
            self.bot.logger.error(f"Error fetching ban info: {e}")
            return None

    @commands.command(name="user")
    async def user_command(self, ctx: commands.Context, username: str = None):
        """
        Fetches and displays information about a Twitch user.
        Usage: #user <username>
        If no username is provided, it shows information about the command user.
        """
        if not username:
            username = ctx.author.name

        try:
            users = await self.bot.fetch_users(names=[username])
            if not users:
                await ctx.send(f"@{ctx.author.name}, no user found with the name '{username}'.")
                return

            user = users[0]
            broadcaster_type = self.format_enum(user.broadcaster_type)
            account_age = self.format_account_age(user.created_at)

            # Fetch ban information
            ban_info = await self.get_ban_info(ctx.channel.id, user.id)

            response = (
                f"@{ctx.author.name}, User info for {user.display_name} (twitch.tv/{user.name}): "
                f"ID: {user.id} | "
                f"Broadcaster Type: {broadcaster_type} | "
                f"Created: {account_age} | "
                f"Bio: {user.description[:100]}{'...' if len(user.description) > 100 else ''} | "
                f"Profile Picture: {user.profile_image}"
            )

            if ban_info:
                ban_type = "Banned" if ban_info.expires_at is None else "Timed out"
                expiry = (
                    f" until {ban_info.expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}" if ban_info.expires_at else ""
                )
                response += (
                    f" | {ban_type} in this channel{expiry} | "
                    f"Reason: {ban_info.reason or 'No reason provided'} | "
                    f"Banned by: {ban_info.moderator.name}"
                )

            await ctx.send(response)
        except Exception as e:
            self.bot.logger.error(f"Error fetching user info: {e}")
            await ctx.send(
                f"@{ctx.author.name}, an error occurred while fetching user information. Please try again later."
            )


def prepare(bot):
    bot.add_cog(User(bot))
