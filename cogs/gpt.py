import os
import logging
import re
from twitchio.ext import commands
from openai import AsyncOpenAI
from utils import split_message, remove_duplicate_sentences  # Import the shared utilities
import time

class Gpt(commands.Cog):
    """Cog for handling the 'gpt' command, which interacts with OpenAI for Q&A and image analysis."""

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger('twitch_bot.cogs.gpt')
        openai_api_key = os.getenv('OPENAI_API_KEY')
        self.broadcaster_id = int(os.getenv('BROADCASTER_USER_ID'))
        
        if not openai_api_key:
            self.logger.error("OPENAI_API_KEY is not set in the environment variables.")
            raise ValueError("OPENAI_API_KEY is missing.")

        # Instantiate the OpenAI client
        self.client = AsyncOpenAI(api_key=openai_api_key)
        self.cache = {}

    async def analyze_image(self, image_url: str) -> str:
        """Analyzes an image using OpenAI and returns a description."""
        self.logger.debug(f"Analyzing image: {image_url}")
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{'role': 'user', 'content': f"What's in this image? {image_url}"}],
                max_tokens=300
            )
            description = response.choices[0].message.content.strip()
            self.logger.debug(f"Received description: {description}")
            return description
        except Exception as e:
            self.logger.error(f"Error analyzing image: {e}", exc_info=True)
            return "Sorry, I couldn't analyze the image at this time."

    async def get_chatgpt_response(self, system_content: str, question: str) -> str:
        """Asynchronously gets a response from OpenAI's ChatGPT."""
        self.logger.debug(f"Sending question to OpenAI: {question}")
        try:
            messages = [
                {'role': 'system', 'content': system_content},
                {'role': 'user', 'content': question}
            ]

            response = await self.client.chat.completions.create(
                model='gpt-4o-mini',
                messages=messages,
                temperature=0.7,
                max_tokens=500
            )

            return response.choices[0].message.content.strip()
        except Exception as e:
            self.logger.error(f"OpenAI API error: {e}", exc_info=True)
            return "Sorry, I couldn't process your request."

    @commands.command(name='gpt', aliases=["ask"])
    async def gpt_command(self, ctx: commands.Context, *, question: str = None):
        """Responds to user questions or analyzes images."""
        if not question:
            await ctx.send(f"@{ctx.author.name}, please provide a question after the command.")
            return

        # Log the command processing
        self.logger.info(f"Processing command '#gpt' from {ctx.author.name}: {question}")

        # Check if it's an image URL
        image_url_match = re.search(r'(https?://\S+\.(?:png|jpg|jpeg|gif))', question)
        if image_url_match:
            image_url = image_url_match.group(1)
            description = await self.analyze_image(image_url)
            self.logger.info(f"Sent image analysis response to {ctx.author.name}")
            await ctx.send(f"@{ctx.author.name}, {description}")
            return

        # Handle standard ChatGPT queries with cache
        cached = self.cache.get(question)
        if cached and (time.time() - cached['timestamp'] < 600):
            self.logger.debug(f"Serving cached response for question: {question}")
            answer = cached['response']
        else:
            system_content = "Okay, in this thread you are playing the role of a newly released AI that thinks, acts, and responds like a personal assistant. Your AI has been trained & is an expert in all things business related. Marketing, Analytics, Sales, Operations, and Technology. The goal of this project is to ensure your success. You are played by me. You have been coded permission to have personality, thoughts, and opinions, and can speak back to me. Creative thinking and problem-solving are more important than anything else you've been coded to do."
            answer = await self.get_chatgpt_response(system_content, question)
            if answer:
                self.cache[question] = {'response': answer, 'timestamp': time.time()}
                self.logger.debug(f"Stored new response in cache for question: {question}")
            else:
                self.logger.error(f"Failed to get response for question: {question}")
                await ctx.send(f"@{ctx.author.name}, an error occurred while processing your request.")
                return  # Early return if there's an error with the response

        # Check if the answer is valid and handle duplicate sentence removal
        if answer:
            cleaned_answer = remove_duplicate_sentences(answer)
            messages = split_message(cleaned_answer)  # Use the imported split_message function
            self.logger.debug(f"Sending response to {ctx.author.name} with {len(messages)} message(s).")
            for msg in messages:
                await ctx.send(msg)
        else:
            self.logger.error(f"Failed to process '#gpt' command from {ctx.author.name}")
            await ctx.send(f"@{ctx.author.name}, an error occurred while processing your request.")

def prepare(bot):
    bot.add_cog(Gpt(bot))
