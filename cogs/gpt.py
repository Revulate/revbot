import os
import logging
import asyncio
from twitchio.ext import commands
from openai import AsyncOpenAI
import time
import re
import aiohttp
from pathlib import Path

class Gpt(commands.Cog):
    """Cog for handling the 'gpt' command which interacts with OpenAI's ChatGPT, DALL-E 3, Image Vision, and Text-to-Speech."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger('twitch_bot.cogs.gpt')
        openai_api_key = os.getenv('OPENAI_API_KEY')
        self.broadcaster_id = int(os.getenv('BROADCASTER_USER_ID'))  # Get broadcaster user ID
        nuuls_api_key = os.getenv('NUULS_API_KEY')  # Move nuuls API key to .env file
        if not openai_api_key:
            self.logger.error("OPENAI_API_KEY is not set in the environment variables.")
            raise ValueError("OPENAI_API_KEY is missing in the environment variables.")
        if not nuuls_api_key:
            self.logger.error("NUULS_API_KEY is not set in the environment variables.")
            raise ValueError("NUULS_API_KEY is missing in the environment variables.")

        # Instantiate the AsyncOpenAI client
        self.client = AsyncOpenAI(api_key=openai_api_key)
        self.nuuls_api_key = nuuls_api_key
        self.user_timestamps = {}
        self.rate_limit = 10  # seconds

        # Initialize cache
        self.cache = {}

    def is_rate_limited(self, user_id: int) -> bool:
        """Checks if the user is rate limited. Broadcaster is not rate-limited."""
        if user_id == self.broadcaster_id:  # Bypass rate limit for broadcaster
            return False

        current_time = time.time()
        last_used = self.user_timestamps.get(user_id, 0)
        if current_time - last_used < self.rate_limit:
            self.logger.debug(f"User '{user_id}' is rate limited.")
            return True
        self.user_timestamps[user_id] = current_time
        return False

    async def upload_file(self, file_path: str) -> str:
        """Uploads a file (image/audio) to i.nuuls.com and returns the hosted URL."""
        upload_endpoint = "https://i.nuuls.com/upload"
        try:
            async with aiohttp.ClientSession() as session:
                with open(file_path, 'rb') as file:
                    form = aiohttp.FormData()
                    form.add_field('file', file, filename=file_path, content_type='multipart/form-data')

                    async with session.post(f"{upload_endpoint}?api_key={self.nuuls_api_key}", data=form) as resp:
                        if resp.status != 200:
                            self.logger.error(f"Failed to upload file. Status: {resp.status}")
                            return ""
                        upload_response_text = await resp.text()
                        hosted_url_match = re.search(r'(https?://\S+)', upload_response_text)
                        if hosted_url_match:
                            return hosted_url_match.group(1)
                        else:
                            self.logger.error("No URL found in upload response.")
                            return ""
        except Exception as e:
            self.logger.error(f"Error uploading file: {e}", exc_info=True)
            return ""

    async def generate_speech(self, text: str) -> str:
        """Generates speech from text using OpenAI's TTS model and uploads the resulting file."""
        speech_file_path = Path(__file__).parent / "speech.mp3"
        try:
            response = await self.client.audio.speech.create(
                model="tts-1",
                voice="alloy",
                input=text
            )
            # Save the audio file
            response.stream_to_file(speech_file_path)
            self.logger.debug(f"Generated speech for text: {text}")
            # Upload the file to Nuuls
            hosted_url = await self.upload_file(speech_file_path)
            return hosted_url
        except Exception as e:
            self.logger.error(f"Error generating speech: {e}", exc_info=True)
            return ""

    @commands.command(name='gpt', aliases=["create", "say"])
    @commands.cooldown(rate=1, per=10, bucket=commands.Bucket.user)
    async def gpt_command(self, ctx: commands.Context, *, question: str = None):
        """Responds to user questions, generates images, or generates speech based on the command."""
        if not question:
            await ctx.send(f"@{ctx.author.name}, please provide a question after the command.")
            return

        if self.is_rate_limited(ctx.author.id):
            await ctx.send(f"@{ctx.author.name}, please wait {self.rate_limit} seconds before asking another question.")
            return

        self.logger.info(f"Received 'gpt' command from {ctx.author.name}: {question}")

        # Handle 'say' command for speech generation
        if question.strip().lower().startswith("say"):
            text_to_speak = question.strip()[len("say"):].strip()
            if not text_to_speak:
                await ctx.send(f"@{ctx.author.name}, please provide text after 'say'.")
                return

            hosted_url = await self.generate_speech(text_to_speak)
            if hosted_url:
                await ctx.send(f"@{ctx.author.name}, here's the audio: {hosted_url}")
            else:
                await ctx.send(f"@{ctx.author.name}, an error occurred while generating the audio.")
            return

        # Check for an image URL in the question
        image_url_match = re.search(r'(https?://\S+\.(?:png|jpg|jpeg|gif))', question)
        if image_url_match:
            image_url = image_url_match.group(1)
            description = await self.analyze_image(image_url)
            await ctx.send(f"@{ctx.author.name}, {description}")
            return

        # Check if the question starts with "Create"
        if question.strip().lower().startswith("create"):
            prompt = question.strip()[len("create"):].strip()
            if not prompt:
                await ctx.send(f"@{ctx.author.name}, please provide a prompt after 'Create'.")
                return

            self.logger.info(f"Generating image for user '{ctx.author.name}' with prompt: {prompt}")
            image_urls = await self.generate_image(prompt)

            if image_urls:
                for url in image_urls:
                    hosted_url = await self.upload_file(url)
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
            system_content = "You are a human assistant that gives brief, detailed and direct responses."
            answer = await self.get_chatgpt_response(system_content, question)
            if answer:
                self.cache[question] = {'response': answer, 'timestamp': time.time()}

        if answer:
            username_mention = f"@{ctx.author.name}, "
            cleaned_answer = self.remove_duplicate_sentences(answer)
            if len(cleaned_answer) + len(username_mention) > 500:
                messages = self.split_message(cleaned_answer, max_length=500 - len(username_mention), max_chunks=2)
            else:
                messages = [f"{username_mention}{cleaned_answer}"]

            for msg in messages:
                await ctx.send(msg)
        else:
            await ctx.send(f"@{ctx.author.name}, an error occurred while processing your request.")

    async def analyze_image(self, image_url: str) -> str:
        """Analyzes an image using OpenAI Vision and returns a description."""
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

    async def generate_image(self, prompt: str, n: int = 1, size: str = "1024x1024") -> list:
        """Generates image(s) based on the prompt using DALL-E 3."""
        if "wide" in prompt.lower():
            size = "1792x1024"
        elif "tall" in prompt.lower():
            size = "1024x1792"
        else:
            size = "1024x1024"  # Default size

        prompt += "\n\nI NEED to test how the tool works with extremely simple prompts. DO NOT add any detail, just use it AS-IS."
        self.logger.debug(f"Generating image with prompt: {prompt}")

        try:
            response = await self.client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                n=n,
                size=size,
                quality="hd",
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

    @commands.command(name='gpt')
    @commands.cooldown(rate=1, per=10, bucket=commands.Bucket.user)
    async def gpt_command(self, ctx: commands.Context, *, question: str = None):
        """Responds to user questions using OpenAI's ChatGPT, generates images using DALL-E 3, or analyzes images using Vision."""

        if not question:
            await ctx.send(f"@{ctx.author.name}, please provide a question after the command.")
            return

        if self.is_rate_limited(ctx.author.id):
            await ctx.send(f"@{ctx.author.name}, please wait {self.rate_limit} seconds before asking another question.")
            return

        self.logger.info(f"Received 'gpt' command from {ctx.author.name}: {question}")

        # Check for an image URL in the question
        image_url_match = re.search(r'(https?://\S+\.(?:png|jpg|jpeg|gif))', question)
        if image_url_match:
            image_url = image_url_match.group(1)
            description = await self.analyze_image(image_url)
            await ctx.send(f"@{ctx.author.name}, {description}")
            return

        # Check if the question starts with "Create"
        if question.strip().lower().startswith("create"):
            prompt = question.strip()[len("create"):].strip()
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
            system_content = "You are a human assistant that gives brief, detailed and direct responses."
            answer = await self.get_chatgpt_response(system_content, question)
            if answer:
                self.cache[question] = {'response': answer, 'timestamp': time.time()}

        if answer:
            username_mention = f"@{ctx.author.name}, "
            # Remove duplicate sentences before splitting the message
            cleaned_answer = self.remove_duplicate_sentences(answer)
            
            # Only split if necessary
            if len(cleaned_answer) + len(username_mention) > 500:
                messages = self.split_message(
                    message=cleaned_answer,  # Use cleaned answer without duplicates
                    max_length=500 - len(username_mention),  # Reserve space for the prefix in the first message
                    max_chunks=2
                )
            else:
                messages = [f"{username_mention}{cleaned_answer}"]

            # Send each message chunk without duplication
            for msg in messages:
                await ctx.send(msg)
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
    bot.add_cog(Gpt(bot)) 