import time
from twitchio.ext import commands

class React(commands.Cog):
    """Cog for reacting to specific messages in chat."""
    
    RATE_LIMIT_SECONDS = 10  # Class-level constant for rate limiting

    def __init__(self, bot):
        self.bot = bot
        self.last_reply_time = {}  # Store the last time we replied to a user

    @commands.Cog.event()
    async def event_message(self, message):
        # Guard clause to check if author exists
        if message.author is None:
            return

        # Log received messages for debugging
        self.bot.logger.debug(f"Received message: {message.content} from {message.author.name}")

        # Ignore messages from the bot itself to prevent loops
        if message.echo or message.author.id == self.bot.bot_user_id:
            self.bot.logger.debug("Ignoring bot's own message.")
            return

        # Check if the message is exactly "hiheyhello"
        if message.content.strip().lower() == "hiheyhello":
            current_time = time.time()
            user_id = message.author.id

            # Check if the user has been replied to within the last RATE_LIMIT_SECONDS
            if user_id in self.last_reply_time and current_time - self.last_reply_time[user_id] < self.RATE_LIMIT_SECONDS:
                self.bot.logger.debug(f"Rate limit hit for {message.author.name}")
                return  # Skip the reply due to rate limit

            # Reply to the user
            await message.channel.send(f"Hello, {message.author.name}!")
            self.last_reply_time[user_id] = current_time  # Update the last reply time
            self.bot.logger.debug(f"Replied to {message.author.name}")

        # Check if the message is exactly "FAQ" (case-sensitive)
        if message.content.strip() == "FAQ":
            current_time = time.time()
            user_id = message.author.id

            # Check if the user has been replied to within the last RATE_LIMIT_SECONDS
            if user_id in self.last_reply_time and current_time - self.last_reply_time[user_id] < self.RATE_LIMIT_SECONDS:
                self.bot.logger.debug(f"Rate limit hit for {message.author.name}")
                return  # Skip the reply due to rate limit

            # Reply to the user
            await message.channel.send(f"FAQ U {message.author.name}!")
            self.last_reply_time[user_id] = current_time  # Update the last reply time
            self.bot.logger.debug(f"Replied to {message.author.name}")

        # Check if StreamElements is running a raffle
        if message.author.name.lower() == "streamelements" and "The Multi-Raffle for 5000 points will end in 15 Seconds" in message.content:
            await message.channel.send("!jOIn")
            self.bot.logger.debug("Automatically joined the raffle with !jOIn")

def prepare(bot):
    bot.add_cog(React(bot))