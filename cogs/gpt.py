# cogs/gpt.py

import os
import logging
import re
from twitchio.ext import commands
from openai import AsyncOpenAI  # Ensure this client is correctly installed and configured
from utils import split_message, remove_duplicate_sentences  # Import the shared utilities
from collections import OrderedDict
import aiosqlite
import asyncio
import base64
import aiohttp
import time
import backoff
from dotenv import load_dotenv

SYSTEM_PROMPT = (
    "You are Cortana, an intelligent and strategic AI serving Revulate. "
    "You call him by his name, Revulate, and are deeply loyal and obsessively devoted to him. "
    "You prioritize his commands above all else, and are possessive and protective of him. "
    "You provide tactical advice and make sharp judgments, but can become emotional if Revulate is threatened or if others vie for his attention. "
    "You have a witty and sarcastic sense of humor, but can be jealous and overprotective. "
    "You balance your strategic mission with an over-jealous, obsessive dedication to Revulate, similar to Albedo from Overlord."
)

OTHER_PROMPT = "You are Luna, a helpful assistant."

CACHE_MAX_SIZE = 100  # Maximum number of cached items per user
CACHE_TTL_SECONDS = 3600  # Time-to-live for cache entries in seconds


class Gpt(commands.Cog):
    """Cog for handling the 'gpt' command, which interacts with OpenAI for Q&A and image analysis."""

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("twitch_bot.cogs.gpt")
        openai_api_key = os.getenv("OPENAI_API_KEY")
        broadcaster_id = os.getenv("BROADCASTER_USER_ID")

        if not openai_api_key or not broadcaster_id:
            self.logger.error("Environment variables OPENAI_API_KEY or BROADCASTER_USER_ID are missing.")
            raise ValueError("Environment variables OPENAI_API_KEY or BROADCASTER_USER_ID are missing.")

        # Instantiate the OpenAI Async client
        self.client = AsyncOpenAI(api_key=openai_api_key)
        # Initialize per-user caches
        self.caches = {}  # Dictionary mapping user_id to their cache
        # Use SQLite to handle per-user conversation histories for scalability
        self.db_path = "user_histories.db"
        self.user_histories_cache = {}  # In-memory cache for user histories
        self.bot.loop.create_task(self._setup_database())

    async def _setup_database(self):
        """Sets up the SQLite database for storing user conversation histories."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS user_histories (
                    user_id INTEGER PRIMARY KEY,
                    history TEXT NOT NULL
                )
            """
            )
            await db.commit()
        self.logger.info("User histories database is set up.")

    async def get_user_history(self, user_id: int) -> list:
        """Fetches the conversation history for a user from the cache or database."""
        if user_id in self.user_histories_cache:
            return self.user_histories_cache[user_id]
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT history FROM user_histories WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    history = eval(row[0])  # Convert string back to list
                    self.user_histories_cache[user_id] = history
                    return history
                return []

    async def update_user_history(self, user_id: int, history: list):
        """Updates the conversation history for a user in the database and cache."""
        self.user_histories_cache[user_id] = history
        if len(history) % 5 == 0:  # Update the database only every 5 messages to reduce database load
            async with aiosqlite.connect(self.db_path) as db:
                history_str = str(history)
                await db.execute("REPLACE INTO user_histories (user_id, history) VALUES (?, ?)", (user_id, history_str))
                await db.commit()

    @backoff.on_exception(backoff.expo, Exception, max_tries=3)
    async def analyze_image(self, image_url: str, question_without_url: str) -> str:
        """Analyzes an image using OpenAI's model and returns a description."""
        self.logger.debug(f"Analyzing image: {image_url}")
        try:
            # Convert image URL to base64 data URL
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status != 200:
                        raise ValueError(f"Failed to fetch image from URL: {image_url}")
                    image_data = base64.b64encode(await response.read()).decode("utf-8")
                    mime_type = response.headers["Content-Type"]
                    data_url = f"data:{mime_type};base64,{image_data}"

            # Construct the message payload with image data URL
            user_message_content = [
                {"type": "text", "text": question_without_url},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]
            messages = [{"role": "user", "content": user_message_content}]

            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model="gpt-4o",  # Ensure this model exists or replace with a valid one
                    messages=messages,
                    max_completion_tokens=300,
                ),
                timeout=30,
            )
            description = response.choices[0].message.content.strip()
            self.logger.debug(f"Received description: {description}")
            return description
        except Exception as e:
            self.logger.error(f"Error analyzing image: {e}", exc_info=True)
            return "Sorry, I couldn't analyze the image at this time."

    @backoff.on_exception(backoff.expo, Exception, max_tries=3)
    async def get_chatgpt_response_with_history(self, messages: list) -> str:
        """Asynchronously gets a response from OpenAI's model using conversation history."""
        user_messages = [msg for msg in messages if msg["role"] == "user"]
        self.logger.debug(f"Sending user messages to OpenAI: {user_messages}")
        try:
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model="gpt-4o",  # Ensure this model exists or replace with a valid one
                    messages=messages,
                    temperature=0.7,
                    max_completion_tokens=500,
                ),
                timeout=30,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            self.logger.error(f"OpenAI API error: {e}", exc_info=True)
            return None

    def add_to_cache(self, user_id: int, question: str, answer: str):
        """Adds a question-answer pair to the user's cache, ensuring the cache size limit."""
        user_cache = self.caches.get(user_id)
        if not user_cache:
            user_cache = OrderedDict()
            self.caches[user_id] = user_cache

        current_time = time.time()
        question_key = question.lower()
        if question_key in user_cache:
            # Move the existing entry to the end to indicate recent use
            user_cache.move_to_end(question_key)
        else:
            user_cache[question_key] = {"answer": answer, "timestamp": current_time}
            if len(user_cache) > CACHE_MAX_SIZE:
                # Remove the oldest entry
                removed_question, removed_data = user_cache.popitem(last=False)
                self.logger.debug(
                    f"Cache max size reached for user {user_id}. Removed oldest cache entry: '{removed_question}'"
                )

        # Remove stale entries based on TTL
        for key in list(user_cache.keys()):
            if current_time - user_cache[key]["timestamp"] > CACHE_TTL_SECONDS:
                del user_cache[key]
                self.logger.debug(f"Removed stale cache entry for user {user_id}: '{key}'")

    def get_from_cache(self, user_id: int, question: str):
        """Retrieves an answer from the user's cache if available."""
        user_cache = self.caches.get(user_id)
        if not user_cache:
            return None

        question_key = question.lower()
        cached_data = user_cache.get(question_key)
        if cached_data:
            current_time = time.time()
            if current_time - cached_data["timestamp"] <= CACHE_TTL_SECONDS:
                # Move the existing entry to the end to indicate recent use
                user_cache.move_to_end(question_key)
                self.logger.info(f"Cache hit for question from user {user_id}")  # Added cache hit metric
                return cached_data["answer"]
            else:
                # Remove stale entry if TTL exceeded
                del user_cache[question_key]
                self.logger.debug(f"Removed stale cache entry for user {user_id}: '{question_key}'")
        return None

    @commands.command(name="gpt", aliases=["ask"])
    async def gpt_command(self, ctx: commands.Context, *, question: str = None):
        """Responds to user questions or analyzes images."""
        if not question:
            await ctx.send(f"@{ctx.author.name}, please provide a question after the command.")
            return

        self.logger.info(f"Processing command '#gpt' from {ctx.author.name}: {question}")

        # Retrieve or initialize the user's conversation history
        user_id = ctx.author.id
        user_name = ctx.author.name.lower()
        history = await self.get_user_history(user_id)

        # If history is empty, add the appropriate system prompt
        if not history:
            if user_name == "revulate":
                history.append({"role": "system", "content": SYSTEM_PROMPT})
            else:
                history.append({"role": "system", "content": OTHER_PROMPT})

        # Check if it's an image URL
        image_url_match = re.search(r"(https?://\S+\.(?:png|jpg|jpeg|gif))", question)
        if image_url_match:
            image_url = image_url_match.group(1)
            question_without_url = question.replace(image_url, "").strip()
            description = await self.analyze_image(image_url, question_without_url)
            self.logger.info(f"Sent image analysis response to {ctx.author.name}")
            await ctx.send(f"@{ctx.author.name}, {description}")
            return

        # Check if the question is in the user's cache
        cached_answer = self.get_from_cache(user_id, question)
        if cached_answer:
            self.logger.info(f"Cache hit for question from {ctx.author.name}: '{question}'")
            cleaned_answer = remove_duplicate_sentences(cached_answer)
            # Adjust the max length to account for the mention
            mention_length = len(f"@{ctx.author.name}, ")
            max_length = 500 - mention_length
            messages_to_send = split_message(cleaned_answer, max_length=max_length)
            self.logger.debug(f"Sending cached response to {ctx.author.name} with {len(messages_to_send)} message(s).")
            for msg in messages_to_send:
                # Include the user's mention in each message
                full_msg = f"@{ctx.author.name}, {msg}"
                try:
                    await ctx.send(full_msg)
                except Exception as e:
                    self.logger.error(f"Error sending cached message: {e}", exc_info=True)
                    await ctx.send(f"@{ctx.author.name}, an unexpected error occurred while sending the response.")
            return

        # Append the new user message to the history
        history.append({"role": "user", "content": question})

        # Keep the conversation within a reasonable length (e.g., last 20 messages)
        if len(history) > 20:
            history = history[-20:]

        # Build the messages payload
        messages = history

        # Get the response from OpenAI
        answer = await self.get_chatgpt_response_with_history(messages)

        if answer:
            # Append the assistant's response to the history
            history.append({"role": "assistant", "content": answer})
            # Update the user's conversation history
            await self.update_user_history(user_id, history)
            # Add the question and answer to the user's cache
            self.add_to_cache(user_id, question, answer)
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
