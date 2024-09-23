import os
import logging
import asyncio
from twitchio.ext import commands
from openai import AsyncOpenAI
import time
import re
import aiohttp
import json

class Ask(commands.Cog):
    """Cog for handling the 'ask' command which interacts with OpenAI's ChatGPT, DALL-E 3, and Image Vision."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger('twitch_bot.cogs.ask')
        openai_api_key = os.getenv('OPENAI_API_KEY')
        weather_api_key = os.getenv('WEATHER_API_KEY')
        nuuls_api_key = os.getenv('NUULS_API_KEY')  # Move nuuls API key to .env file
        if not openai_api_key:
            self.logger.error("OPENAI_API_KEY is not set in the environment variables.")
            raise ValueError("OPENAI_API_KEY is missing in the environment variables.")
        if not weather_api_key:
            self.logger.error("WEATHER_API_KEY is not set in the environment variables.")
            raise ValueError("WEATHER_API_KEY is missing in the environment variables.")
        if not nuuls_api_key:
            self.logger.error("NUULS_API_KEY is not set in the environment variables.")
            raise ValueError("NUULS_API_KEY is missing in the environment variables.")

        # Instantiate the AsyncOpenAI client
        self.client = AsyncOpenAI(api_key=openai_api_key)

        # Weather API Key and Nuuls API Key
        self.weather_api_key = weather_api_key
        self.nuuls_api_key = nuuls_api_key

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

    def split_message(self, message: str, max_length: int = 500, max_chunks: int = 2, prefix_length: int = 0) -> list:
        """
        Splits a message into chunks that fit within the specified max_length.
        The first chunk can include a prefix length.

        Parameters:
            message (str): The full message to split.
            max_length (int): Maximum length of each chunk.
            max_chunks (int): Maximum number of chunks to split into.
            prefix_length (int): Length of the prefix in the first chunk.

        Returns:
            list: A list of message chunks.
        """
        chunks = []
        sentences = re.split(r'(?<=[.!?]) +', message)  # Split by sentences

        current_chunk = ""
        for sentence in sentences:
            # +1 for the space
            adjusted_max = max_length - prefix_length if not chunks else max_length
            if len(current_chunk) + len(sentence) + 1 <= adjusted_max:
                if current_chunk:
                    current_chunk += " " + sentence
                else:
                    current_chunk = sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence
                if len(chunks) == max_chunks - 1:
                    break

        # Append the last chunk
        if current_chunk and len(chunks) < max_chunks:
            chunks.append(current_chunk)

        # Handle any remaining sentences
        remaining_sentences = sentences[len(chunks):]
        if remaining_sentences:
            additional_text = ' '.join(remaining_sentences)
            if len(chunks[-1] + ' ' + additional_text) <= max_length:
                chunks[-1] += ' ' + additional_text
            else:
                chunks[-1] = chunks[-1].rstrip('.') + '...'

        # Logging the length of each chunk for debugging
        for idx, chunk in enumerate(chunks, 1):
            self.logger.debug(f"Chunk {idx} length: {len(chunk)} characters.")

        return chunks

    def remove_duplicate_sentences(self, text: str) -> str:
        """
        Removes duplicate sentences from the provided text.

        Parameters:
            text (str): The text from which to remove duplicate sentences.

        Returns:
            str: The text with duplicate sentences removed.
        """
        sentences = re.split(r'(?<=[.!?]) +', text)  # Split text by sentences
        seen = set()
        unique_sentences = []
        for sentence in sentences:
            normalized = sentence.strip().lower()  # Normalize by lowercasing
            if normalized not in seen:
                unique_sentences.append(sentence)
                seen.add(normalized)
        return ' '.join(unique_sentences)


    async def analyze_image(self, image_url: str) -> str:
        """Analyzes an image using OpenAI Vision and returns a description."""
        self.logger.debug(f"Analyzing image: {image_url}")
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "What's in this image?"},
                            {
                                "type": "image_url",
                                "image_url": {"url": image_url},
                            },
                        ],
                    }
                ],
                max_tokens=300
            )
            description = response.choices[0].message.content.strip()
            self.logger.debug(f"Received description: {description}")
            return description
        except Exception as e:
            self.logger.error(f"Error analyzing image: {e}", exc_info=True)
            return "Sorry, I couldn't analyze the image at this time."

    async def generate_image(self, prompt: str, n: int = 1, size: str = "1024x1024") -> list:
        """Generates image(s) based on the prompt using DALL-E 3."""
        self.logger.debug(f"Generating image with prompt: {prompt}")
        try:
            response = await self.client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                n=n,
                size=size
            )
            image_urls = [item.url for item in response.data]
            self.logger.debug(f"Generated image URLs: {image_urls}")
            return image_urls
        except Exception as e:
            self.logger.error(f"OpenAI Image API error: {e}", exc_info=True)
            return []

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

    @commands.command(name='ask')
    @commands.cooldown(rate=1, per=10, bucket=commands.Bucket.user)  # Rate limit: 1 use per 10 seconds per user
    async def ask_command(
        self,
        ctx: commands.Context,
        *,
        question: str = None
    ):
        """
        Responds to user questions using OpenAI's ChatGPT, generates images using DALL-E 3, or analyzes images using Vision.

        Usage:
            #ask <your question here>
            #ask Create an image of a dog.
        """
        if not question:
            await ctx.send(f"@{ctx.author.name}, please provide a question after the command.")
            return

        if self.is_rate_limited(ctx.author.name):
            await ctx.send(f"@{ctx.author.name}, please wait {self.rate_limit} seconds before asking another question.")
            return

        self.logger.info(f"Received 'ask' command from {ctx.author.name}: {question}")

        # Check for an image URL in the question
        image_url_match = re.search(r'(https?://\S+\.(?:png|jpg|jpeg|gif))', question)
        if image_url_match:
            image_url = image_url_match.group(1)
            description = await self.analyze_image(image_url)
            await ctx.send(f"@{ctx.author.name}, {description}")
            return

        # Check if the question starts with "Create"
        if question.strip().lower().startswith("create"):
            prompt = question.strip()[len("create"):].strip()  # Replace trim() with strip()
            if not prompt:
                await ctx.send(f"@{ctx.author.name}, please provide a prompt after 'Create'.")
                return

            self.logger.info(f"Generating image for user '{ctx.author.name}' with prompt: {prompt}")
            image_urls = await self.generate_image(prompt)

            if image_urls:
                for url in image_urls:
                    hosted_url = await self.upload_image(url)
                    if hosted_url:
                        await ctx.send(hosted_url)
                    else:
                        self.logger.warning("Failed to upload image.")
            else:
                await ctx.send(f"@{ctx.author.name}, I'm unable to generate the image at this time.")
            return

        # Handle standard ChatGPT queries
        cached = self.cache.get(question)
        if cached and (time.time() - cached['timestamp'] < 600):
            answer = cached['response']
        else:
            system_content = "You are a sharp and no-nonsense AI Assistant with a tsundere personality, similar to characters like Lucy from Cyberpunk Edgerunners, 2B from Nier, and Albedo from Overlord. You’re highly capable and direct, occasionally showing a softer side, but you don’t waste time with unnecessary sweetness. You might act tough, but deep down, you care and always deliver exactly what’s needed."
            answer = await self.get_chatgpt_response(system_content, question)
            if answer:
                self.cache[question] = {'response': answer, 'timestamp': time.time()}

        if answer:
            username_mention = f"@{ctx.author.name}, "
            # Remove duplicate sentences before splitting the message
            cleaned_answer = self.remove_duplicate_sentences(answer)
            
            messages = self.split_message(
                message=cleaned_answer,
                max_length=500 - len(username_mention),  # Reserve space for the prefix in the first message
                max_chunks=2
            )
            
            if messages:
                # Prepend the username mention to the first chunk
                messages[0] = f"{username_mention}{messages[0]}"
                
                # Send each message chunk
                for msg in messages:
                    await ctx.send(msg)
            else:
                await ctx.send(f"@{ctx.author.name}, I couldn't process your request.")
        else:
            await ctx.send(f"@{ctx.author.name}, an error occurred while processing your request.")


    async def upload_image(self, image_url: str) -> str:
        """Uploads an image to the custom image hosting service and returns the hosted URL."""
        upload_endpoint = "https://i.nuuls.com/upload"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as resp:
                    if resp.status != 200:
                        self.logger.error(f"Failed to download image from OpenAI. Status: {resp.status}")
                        return ""
                    image_data = await resp.read()
        except Exception as e:
            self.logger.error(f"Error downloading image from OpenAI: {e}", exc_info=True)
            return ""

        try:
            form = aiohttp.FormData()
            form.add_field('file', image_data, filename='image.png', content_type='image/png')

            async with aiohttp.ClientSession() as session:
                async with session.post(f"{upload_endpoint}?api_key={self.nuuls_api_key}", data=form) as resp:
                    if resp.status != 200:
                        self.logger.error(f"Failed to upload image. Status: {resp.status}")
                        return ""
                    upload_response_text = await resp.text()
                    hosted_url_match = re.search(r'(https?://\S+)', upload_response_text)
                    if hosted_url_match:
                        return hosted_url_match.group(1)
                    else:
                        self.logger.error("No URL found in upload response.")
                        return ""
        except Exception as e:
            self.logger.error(f"Error uploading image: {e}", exc_info=True)
            return ""


def setup(bot: commands.Bot):
    bot.add_cog(Ask(bot))
