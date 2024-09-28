import os
import logging
import re
from twitchio.ext import commands
from openai import AsyncOpenAI  # Import the AsyncOpenAI client
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

        # Instantiate the OpenAI Async client
        self.client = AsyncOpenAI(api_key=openai_api_key)
        self.cache = {}
        self.user_histories = {}  # For per-user memory

    async def analyze_image(self, image_url: str, question_without_url: str) -> str:
        """Analyzes an image using OpenAI's gpt-4o model and returns a description."""
        self.logger.debug(f"Analyzing image: {image_url}")
        try:
            user_message_content = [
                {"type": "text", "text": question_without_url},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image_url,
                    }
                },
            ]
            messages = [{'role': 'user', 'content': user_message_content}]

            response = await self.client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                max_completion_tokens=300,
                logprobs=False,
            )
            description = response.choices[0].message.content.strip()
            self.logger.debug(f"Received description: {description}")
            return description
        except Exception as e:
            self.logger.error(f"Error analyzing image: {e}", exc_info=True)
            return "Sorry, I couldn't analyze the image at this time."

    async def get_chatgpt_response_with_history(self, messages: list) -> str:
        """Asynchronously gets a response from OpenAI's gpt-4o model using conversation history."""
        self.logger.debug(f"Sending messages to OpenAI: {messages}")
        try:
            response = await self.client.chat.completions.create(
                model='gpt-4o',
                messages=messages,
                temperature=0.7,
                max_completion_tokens=500,
                logprobs=True,
                top_logprobs=2,
            )
            # Access logprobs if needed
            # logprobs = response.choices[0].logprobs
            return response.choices[0].message.content.strip()
        except Exception as e:
            self.logger.error(f"OpenAI API error: {e}", exc_info=True)
            return None

    @commands.command(name='gpt', aliases=["ask"])
    async def gpt_command(self, ctx: commands.Context, *, question: str = None):
        """Responds to user questions or analyzes images."""
        if not question:
            await ctx.send(f"@{ctx.author.name}, please provide a question after the command.")
            return

        self.logger.info(f"Processing command '#gpt' from {ctx.author.name}: {question}")

        # Retrieve or initialize the user's conversation history
        user_id = ctx.author.id
        history = self.user_histories.get(user_id, [])

        # Check if it's an image URL
        image_url_match = re.search(r'(https?://\S+\.(?:png|jpg|jpeg|gif))', question)
        if image_url_match:
            image_url = image_url_match.group(1)
            question_without_url = question.replace(image_url, '').strip()
            description = await self.analyze_image(image_url, question_without_url)
            self.logger.info(f"Sent image analysis response to {ctx.author.name}")
            await ctx.send(f"@{ctx.author.name}, {description}")
            return

        # Append the new user message to the history
        history.append({'role': 'user', 'content': question})

        # Keep the conversation within a reasonable length (e.g., last 20 messages)
        if len(history) > 20:
            history = history[-20:]

        # Build the messages payload
        messages = history

        # Get the response from OpenAI
        answer = await self.get_chatgpt_response_with_history(messages)

        if answer:
            # Append the assistant's response to the history
            history.append({'role': 'assistant', 'content': answer})
            # Update the user's conversation history
            self.user_histories[user_id] = history
            # Send the response
            cleaned_answer = remove_duplicate_sentences(answer)
            # Adjust the max length to account for the mention
            mention_length = len(f"@{ctx.author.name}, ")
            max_length = 500 - mention_length
            messages_to_send = split_message(cleaned_answer, max_length=max_length)
            self.logger.debug(f"Sending response to {ctx.author.name} with {len(messages_to_send)} message(s).")
            for msg in messages_to_send:
                # Include the user's mention in each message
                full_msg = f"@{ctx.author.name}, {msg}"
                try:
                    await ctx.send(full_msg)
                except Exception as e:
                    self.logger.error(f"Error sending message: {e}", exc_info=True)
                    await ctx.send(f"@{ctx.author.name}, an unexpected error occurred while sending the response.")
        else:
            self.logger.error(f"Failed to process '#gpt' command from {ctx.author.name}")
            await ctx.send(f"@{ctx.author.name}, an error occurred while processing your request.")

def prepare(bot):
    bot.add_cog(Gpt(bot))
