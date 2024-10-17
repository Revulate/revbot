import os
from dotenv import load_dotenv
from twitchio.ext import commands
from asyncio import sleep
from datetime import datetime, timezone
from logger import log_info, log_error, log_warning, log_debug

load_dotenv()


class Preview(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.client_id = os.getenv("TWITCH_CLIENT_ID")
        self.client_secret = os.getenv("TWITCH_CLIENT_SECRET")
        if not self.client_id or not self.client_secret:
            raise ValueError("TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET must be set in the environment variables.")

    async def get_channel_info(self, channel_name):
        try:
            users = await self.bot.fetch_users(names=[channel_name])
            if not users:
                return None
            user = users[0]

            channels = await self.bot.fetch_channels([user.id])
            if not channels:
                return None
            channel_info = channels[0]

            streams = await self.bot.fetch_streams(user_ids=[user.id])
            stream_data = streams[0] if streams else None

            videos = await self.bot.fetch_videos(user_id=user.id, type="archive")
            last_video = videos[0] if videos else None

            return {"user": user, "channel_info": channel_info, "stream_data": stream_data, "last_video": last_video}
        except Exception as e:
            log_error(f"Error fetching channel info: {e}")
            return None

    def format_duration(self, duration):
        if not duration:
            return "Unknown duration"
        days, seconds = duration.days, duration.seconds
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if seconds > 0 or not parts:
            parts.append(f"{seconds}s")

        return " ".join(parts)

    @commands.command(name="preview")
    async def preview_command(self, ctx: commands.Context, channel_name: str):
        if not channel_name:
            await ctx.send(f"@{ctx.author.name}, please provide a channel name to get the preview information.")
            return

        retry_count = 3
        for attempt in range(retry_count):
            try:
                log_debug(f"Getting info for channel '{channel_name}' (Attempt {attempt + 1})")
                channel_data = await self.get_channel_info(channel_name)

                if not channel_data:
                    log_error(f"Invalid or missing channel information for '{channel_name}'.")
                    await ctx.send(
                        f"@{ctx.author.name}, could not retrieve valid channel information for '{channel_name}'. Please ensure the channel name is correct."
                    )
                    return

                user = channel_data["user"]
                channel_info = channel_data["channel_info"]
                stream_data = channel_data["stream_data"]
                last_video = channel_data["last_video"]

                now = datetime.now(timezone.utc)
                if stream_data:
                    duration = now - stream_data.started_at if stream_data.started_at else None
                    status = f"LIVE ({self.format_duration(duration)})" if duration else "LIVE"
                    viewers = f"{stream_data.viewer_count:,} viewers"

                    thumbnail_url = stream_data.thumbnail_url.replace("{width}", "").replace("{height}", "")

                    response = (
                        f"@{ctx.author.name}, twitch.tv/{user.name} | "
                        f"Status: {status} | "
                        f"Viewers: {viewers} | "
                        f"Category: {channel_info.game_name} | "
                        f"Title: {channel_info.title} | "
                        f"Preview: {thumbnail_url}"
                    )
                    log_info(f"Sending preview response for {channel_name}: {response}")
                    await ctx.send(response)
                else:
                    status = "OFFLINE"
                    last_live = "Unknown"
                    if last_video:
                        time_since_live = now - last_video.created_at
                        last_live = self.format_duration(time_since_live)

                    response = (
                        f"@{ctx.author.name}, twitch.tv/{user.name} | "
                        f"Status: {status} | "
                        f"Last Live: {last_live} ago | "
                        f"Category: {channel_info.game_name} | "
                        f"Title: {channel_info.title}"
                    )
                    log_info(f"Sending offline preview response for {channel_name}: {response}")
                    await ctx.send(response)

                log_debug(f"Sent preview info for '{channel_name}' to chat.")
                break
            except Exception as e:
                log_error(f"Attempt {attempt + 1} failed with error: {e}")
                if attempt < retry_count - 1:
                    await sleep(2)
                else:
                    await ctx.send(
                        f"@{ctx.author.name}, an error occurred while processing your request. Please try again later."
                    )


def prepare(bot):
    bot.add_cog(Preview(bot))
