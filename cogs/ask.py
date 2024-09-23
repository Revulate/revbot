# cogs/ask.py
import os
import logging
import asyncio
import aiohttp
from typing import Annotated
from twitchio.ext import commands
import openai
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
    """Cog for handling the 'ask' and 'gpt' commands which interact with OpenAI's ChatGPT."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger('twitch_bot.cogs.ask')
        openai.api_key = os.getenv('OPENAI_API_KEY')
        if not openai.api_key:
            self.logger.error("OPENAI_API_KEY is not set in the environment variables.")

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

    async def get_chatgpt_response(self, system_content: str, question: str) -> str:
        """Asynchronously gets a response from OpenAI's ChatGPT."""
        self.logger.debug(f"Sending question to OpenAI: {question}")
        try:
            response = await openai.ChatCompletion.acreate(
                model='gpt-4o-mini',  # Using gpt-4o-mini model
                messages=[
                    {'role': 'system', 'content': system_content},
                    {'role': 'user', 'content': question}
                ],
                temperature=0.7,
                max_tokens=750  # Increased max_tokens to accommodate longer responses before truncation
            )
            answer = response.choices[0].message['content'].strip()
            self.logger.debug(f"Received response from OpenAI: {answer}")
            return answer
        except openai.error.OpenAIError as e:
            self.logger.error(f"OpenAI API error: {e}", exc_info=True)
            return None

    @commands.command(name='ask')
    @commands.cooldown(rate=1, per=10, bucket=commands.Bucket.user)  # Corrected keyword argument
    async def ask_command(
        self,
        ctx: commands.Context,
        *,
        question: str = None
    ):
        """
        Responds to user questions using OpenAI's ChatGPT.

        Usage:
            !ask <your question here>
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
            # Calculate remaining characters after adding the username mention
            username_mention = f"@{ctx.author.name}, "
            max_answer_length = 500 - len(username_mention)
            if len(answer) > max_answer_length:
                self.logger.debug(f"Answer length {len(answer)} exceeds {max_answer_length}. Truncating.")
                answer = answer[:max_answer_length - 3] + '...'
            reply = f"{username_mention}{answer}"
            await ctx.send(reply)
            self.logger.info(f"Sent response to {ctx.author.name}: {answer}")
        else:
            await ctx.send(f"@{ctx.author.name}, an error occurred while processing your request.")
            self.logger.error(f"Failed to get response from OpenAI for user '{ctx.author.name}': {question}")

    @commands.command(name='gpt')
    @commands.cooldown(rate=1, per=10, bucket=commands.Bucket.user)  # Corrected keyword argument
    async def gpt_command(
        self,
        ctx: commands.Context,
        *,
        arg: str = None
    ):
        """
        Responds to user questions as a specified character using OpenAI's ChatGPT.

        Usage:
            ,gpt <Character> <your question here>
        """
        if not arg:
            await ctx.send(f"@{ctx.author.name}, please provide a character and a question.")
            self.logger.warning(f"User '{ctx.author.name}' invoked 'gpt' without arguments.")
            return

        # Use regex to extract character name within angle brackets and the question
        match = re.match(r'<(.+?)>\s+(.+)', arg)
        if not match:
            await ctx.send(f"@{ctx.author.name}, please use the format: ,gpt <Character> <your question here>")
            self.logger.warning(f"User '{ctx.author.name}' used incorrect format for 'gpt' command.")
            return

        character, question = match.groups()

        if not question:
            await ctx.send(f"@{ctx.author.name}, please provide a question after the character.")
            self.logger.warning(f"User '{ctx.author.name}' invoked 'gpt' without a question.")
            return

        if self.is_rate_limited(ctx.author.name):
            await ctx.send(f"@{ctx.author.name}, please wait {self.rate_limit} seconds before asking another question.")
            return

        self.logger.info(f"Received 'gpt' command from {ctx.author.name}: Character='{character}', Question='{question}'")

        # Check cache first with a unique key combining character and question
        cache_key = f"{character}:{question}"
        if cache_key in self.cache:
            answer = self.cache[cache_key]
            self.logger.info(f"Cache hit for gpt command: Character='{character}', Question='{question}'")
        else:
            system_content = f"You are {character}."
            answer = await self.get_chatgpt_response(system_content, question)
            if answer:
                self.cache[cache_key] = answer
                self.logger.info(f"Cache updated for gpt command: Character='{character}', Question='{question}'")

        if answer:
            # Calculate remaining characters after adding the username mention
            username_mention = f"@{ctx.author.name}, "
            max_answer_length = 500 - len(username_mention)
            if len(answer) > max_answer_length:
                self.logger.debug(f"Answer length {len(answer)} exceeds {max_answer_length}. Truncating.")
                answer = answer[:max_answer_length - 3] + '...'
            reply = f"{username_mention}{answer}"
            await ctx.send(reply)
            self.logger.info(f"Sent response to {ctx.author.name} as '{character}': {answer}")
        else:
            await ctx.send(f"@{ctx.author.name}, an error occurred while processing your request.")
            self.logger.error(f"Failed to get response from OpenAI for user '{ctx.author.name}' as '{character}': {question}")

# Removed the share_command method as per the user's request

def setup(bot: commands.Bot):
    bot.add_cog(Ask(bot))
