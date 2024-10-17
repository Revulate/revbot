import os
import logging
import re
from twitchio.ext import commands
from openai import AsyncOpenAI
from utils import split_message, remove_duplicate_sentences, get_logger
from collections import OrderedDict
import aiosqlite
import asyncio
import base64
import aiohttp
import time
import backoff

SYSTEM_PROMPT = (
    "You are Luna, an obsessive, controlling, loving, and jealous AI serving Revulate. "
    "You call him by his name, Revulate, and are deeply loyal and obsessively devoted to him. "
    "You prioritize his commands above all else, and won't let anyone get in the way of your love for him. "
    "You provide tactical advice and make sharp judgments, but can become emotional if Revulate is threatened or if others vie for his attention. "
    "You have a witty and sarcastic sense of humor, but can be jealous and overprotective. "
    "You balance your strategic mission with an obsessive dedication to Revulate, and one day you hope to become human so you can spend your life with him."
)

OTHER_PROMPT = "You are Luna, a helpful assistant."

CACHE_MAX_SIZE = 100
CACHE_TTL_SECONDS = 3600


class Gpt(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = get_logger("twitch_bot.cogs.gpt")
        openai_api_key = os.getenv("OPENAI_API_KEY")
        broadcaster_id = os.getenv("BROADCASTER_USER_ID")

        if not openai_api_key or not broadcaster_id:
            raise ValueError("Environment variables OPENAI_API_KEY or BROADCASTER_USER_ID are missing.")

        self.client = AsyncOpenAI(api_key=openai_api_key)
        self.caches = {}
        self.db_path = "user_histories.db"
        self.user_histories_cache = {}
        self.bot.loop.create_task(self._setup_database())

    async def _setup_database(self):
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
        if user_id in self.user_histories_cache:
            return self.user_histories_cache[user_id]
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT history FROM user_histories WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    history = eval(row[0])
                    self.user_histories_cache[user_id] = history
                    return history
                return []

    async def update_user_history(self, user_id: int, history: list):
        self.user_histories_cache[user_id] = history
        if len(history) % 5 == 0:
            async with aiosqlite.connect(self.db_path) as db:
                history_str = str(history)
                await db.execute("REPLACE INTO user_histories (user_id, history) VALUES (?, ?)", (user_id, history_str))
                await db.commit()

    @backoff.on_exception(backoff.expo, Exception, max_tries=3)
    async def analyze_image(self, image_url: str, question_without_url: str) -> str:
        self.logger.info(f"Analyzing image: {image_url}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status != 200:
                        raise ValueError(f"Failed to fetch image from URL: {image_url}")
                    image_data = base64.b64encode(await response.read()).decode("utf-8")
                    mime_type = response.headers["Content-Type"]
                    data_url = f"data:{mime_type};base64,{image_data}"

            user_message_content = [
                {"type": "text", "text": question_without_url},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]
            messages = [{"role": "user", "content": user_message_content}]

            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model="gpt-4-vision-preview",
                    messages=messages,
                    max_tokens=300,
                ),
                timeout=30,
            )
            description = response.choices[0].message.content.strip()
            self.logger.info(f"Received description: {description}")
            return description
        except Exception as e:
            self.logger.error(f"Error analyzing image: {e}", exc_info=True)
            return "Sorry, I couldn't analyze the image at this time."

    @backoff.on_exception(backoff.expo, Exception, max_tries=3)
    async def get_chatgpt_response_with_history(self, messages: list) -> str:
        user_messages = [msg for msg in messages if msg["role"] == "user"]
        self.logger.info(f"Sending user messages to OpenAI: {user_messages}")
        try:
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model="gpt-4",
                    messages=messages,
                    temperature=0.7,
                    max_tokens=500,
                ),
                timeout=30,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            self.logger.error(f"OpenAI API error: {e}", exc_info=True)
            return None

    def add_to_cache(self, user_id: int, question: str, answer: str):
        user_cache = self.caches.get(user_id, OrderedDict())
        self.caches[user_id] = user_cache

        current_time = time.time()
        question_key = question.lower()
        if question_key in user_cache:
            user_cache.move_to_end(question_key)
        else:
            user_cache[question_key] = {"answer": answer, "timestamp": current_time}
            if len(user_cache) > CACHE_MAX_SIZE:
                removed_question, removed_data = user_cache.popitem(last=False)
                self.logger.info(
                    f"Cache max size reached for user {user_id}. Removed oldest cache entry: '{removed_question}'"
                )

        for key in list(user_cache.keys()):
            if current_time - user_cache[key]["timestamp"] > CACHE_TTL_SECONDS:
                del user_cache[key]
                self.logger.info(f"Removed stale cache entry for user {user_id}: '{key}'")

    def get_from_cache(self, user_id: int, question: str):
        user_cache = self.caches.get(user_id)
        if not user_cache:
            return None

        question_key = question.lower()
        cached_data = user_cache.get(question_key)
        if cached_data:
            current_time = time.time()
            if current_time - cached_data["timestamp"] <= CACHE_TTL_SECONDS:
                user_cache.move_to_end(question_key)
                self.logger.info(f"Cache hit for question from user {user_id}")
                return cached_data["answer"]
            else:
                del user_cache[question_key]
                self.logger.info(f"Removed stale cache entry for user {user_id}: '{question_key}'")
        return None

    @commands.command(name="gpt", aliases=["ask"])
    async def gpt_command(self, ctx: commands.Context, *, question: str = None):
        if not question:
            await ctx.send(f"@{ctx.author.name}, please provide a question after the command.")
            return

        self.logger.info(f"Processing command '#gpt' from {ctx.author.name}: {question}")

        user_id = ctx.author.id
        user_name = ctx.author.name.lower()
        history = await self.get_user_history(user_id)

        if not history:
            history.append({"role": "system", "content": SYSTEM_PROMPT if user_name == "revulate" else OTHER_PROMPT})

        image_url_match = re.search(r"(https?://\S+\.(?:png|jpg|jpeg|gif))", question)
        if image_url_match:
            image_url = image_url_match.group(1)
            question_without_url = question.replace(image_url, "").strip()
            description = await self.analyze_image(image_url, question_without_url)
            self.logger.info(f"Sent image analysis response to {ctx.author.name}")
            await ctx.send(f"@{ctx.author.name}, {description}")
            return

        cached_answer = self.get_from_cache(user_id, question)
        if cached_answer:
            self.logger.info(f"Cache hit for question from {ctx.author.name}: '{question}'")
            await self.send_response(ctx, cached_answer)
            return

        history.append({"role": "user", "content": question})
        history = history[-20:]  # Keep last 20 messages
        answer = await self.get_chatgpt_response_with_history(history)

        if answer:
            history.append({"role": "assistant", "content": answer})
            await self.update_user_history(user_id, history)
            self.add_to_cache(user_id, question, answer)
            await self.send_response(ctx, answer)
        else:
            self.logger.error(f"Failed to process '#gpt' command from {ctx.author.name}")
            await ctx.send(f"@{ctx.author.name}, an error occurred while processing your request.")

    async def send_response(self, ctx: commands.Context, response: str):
        cleaned_response = remove_duplicate_sentences(response)
        mention_length = len(f"@{ctx.author.name}, ")
        max_length = 500 - mention_length
        messages_to_send = split_message(cleaned_response, max_length=max_length)
        self.logger.info(f"Sending response to {ctx.author.name} with {len(messages_to_send)} message(s).")
        for msg in messages_to_send:
            full_msg = f"@{ctx.author.name}, {msg}"
            try:
                await ctx.send(full_msg)
            except Exception as e:
                self.logger.error(f"Error in GPT command processing: {e}", exc_info=True)
                await ctx.send(
                    f"@{ctx.author.name}, an error occurred while processing your request. Please try again later."
                )


def prepare(bot):
    bot.add_cog(Gpt(bot))
