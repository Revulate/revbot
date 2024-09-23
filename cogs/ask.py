# cogs/ask.py
import os
import logging
import asyncio
from twitchio.ext import commands
from openai import AsyncOpenAI
import time
import re

class YoutubeConverterError(commands.BadArgument):
    """Custom exception for invalid YouTube URLs."""
    def __init__(self, link: str):
        self.link = link
        super().__init__("Invalid YouTube URL provided.")

def youtube_converter(ctx: commands.Context, arg: str) -> str:
    """Validates if the provided argument is a YouTube URL."""
    if 'youtube.com' in arg or 'youtu.be' in arg:
        return arg
    else:
        raise YoutubeConverterError(arg)

class Ask(commands.Cog):
    """Cog for handling the 'ask' command which interacts with OpenAI's ChatGPT."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger('twitch_bot.cogs.ask')
        openai_api_key = os.getenv('OPENAI_API_KEY')
        if not openai_api_key:
            self.logger.error("OPENAI_API_KEY is not set in the environment variables.")
            raise ValueError("OPENAI_API_KEY is missing in the environment variables.")

        # Instantiate the AsyncOpenAI client
        self.client = AsyncOpenAI(
            api_key=openai_api_key
            # You can add other parameters here if needed, such as organization, base_url, etc.
        )

        # Rate limiting: user -> last command timestamp
        self.user_timestamps = {}
        self.rate_limit = 10  # seconds

        # Initialize cache
        self.cache = {}

    def is_rate_limited(self, user: str) -> bool:
        """Checks if the user is rate limited."""
        current_time = time.time()
        last_used = self.user_timestamps.get(user, 0)
        if current_time - last_used < self.rate_limit:
            self.logger.debug(f"User '{user}' is rate limited.")
            return True
        self.user_timestamps[user] = current_time
        return False

    def split_message(self, message: str, max_length: int = 500, max_chunks: int = 2) -> list:
        """
        Splits a message into chunks that fit within the specified max_length.
        Allows up to max_chunks messages.
        """
        if len(message) <= max_length:
            return [message]

        chunks = []
        sentences = re.split(r'(?<=[.!?]) +', message)  # Split by sentences

        current_chunk = ""
        for sentence in sentences:
            if len(current_chunk) + len(sentence) + 1 <= max_length:
                if current_chunk:
                    current_chunk += " " + sentence
                else:
                    current_chunk = sentence
            else:
                chunks.append(current_chunk)
                current_chunk = sentence
                if len(chunks) == max_chunks - 1:
                    break

        # Append the last chunk
        if current_chunk and len(chunks) < max_chunks:
            chunks.append(current_chunk)

        # If there are remaining sentences, append them to the last chunk with ellipsis
        remaining_sentences = sentences[len(chunks):]
        if remaining_sentences:
            additional_text = ' '.join(remaining_sentences)
            if len(chunks[-1] + ' ' + additional_text) <= max_length:
                chunks[-1] += ' ' + additional_text
            else:
                chunks[-1] = chunks[-1].rstrip('.') + '...'

        return chunks

    async def get_chatgpt_response(self, system_content: str, question: str) -> str:
        """Asynchronously gets a response from OpenAI's ChatGPT."""
        self.logger.debug(f"Sending question to OpenAI: {question}")
        try:
            response = await self.client.chat.completions.create(
                model='gpt-4o-mini',  # Ensure this model name is correct and available
                messages=[
                    {'role': 'system', 'content': system_content},
                    {'role': 'user', 'content': question}
                ],
                temperature=0.7,
                max_tokens=750  # Adjust as needed
            )
            answer = response.choices[0].message.content.strip()
            self.logger.debug(f"Received response from OpenAI: {answer}")
            return answer
        except Exception as e:
            self.logger.error(f"OpenAI API error: {e}", exc_info=True)
            return None

    @commands.command(name='ask')
    @commands.cooldown(rate=1, per=10, bucket=commands.Bucket.user)  # Rate limit: 1 use per 10 seconds per user
    async def ask_command(
        self,
        ctx: commands.Context,
        *,
        question: str = None
    ):
        """
        Responds to user questions using OpenAI's ChatGPT.

        Usage:
            ,ask <your question here>
        """
        if not question:
            await ctx.send(f"@{ctx.author.name}, please provide a question after the command.")
            self.logger.warning(f"User '{ctx.author.name}' invoked 'ask' without a question.")
            return

        if self.is_rate_limited(ctx.author.name):
            await ctx.send(f"@{ctx.author.name}, please wait {self.rate_limit} seconds before asking another question.")
            return

        self.logger.info(f"Received 'ask' command from {ctx.author.name}: {question}")

        # Check cache first
        if question in self.cache:
            answer = self.cache[question]
            self.logger.info(f"Cache hit for question: {question}")
        else:
            system_content = "You are a Teacher about Artificial Intelligence."
            answer = await self.get_chatgpt_response(system_content, question)
            if answer:
                self.cache[question] = answer
                self.logger.info(f"Cache updated for question: {question}")

        if answer:
            # Prepare the full reply
            username_mention = f"@{ctx.author.name}, "
            full_reply = f"{username_mention}{answer}"

            # Split the message into chunks
            messages = self.split_message(full_reply, max_length=500, max_chunks=2)

            for msg in messages:
                await ctx.send(msg)
                self.logger.info(f"Sent response to {ctx.author.name}: {msg}")
        else:
            await ctx.send(f"@{ctx.author.name}, an error occurred while processing your request.")
            self.logger.error(f"Failed to get response from OpenAI for user '{ctx.author.name}': {question}")

def setup(bot: commands.Bot):
    bot.add_cog(Ask(bot))
