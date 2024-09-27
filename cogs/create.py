import os
import logging
import aiohttp
import re
from twitchio.ext import commands
from openai import AsyncOpenAI
from utils import split_message  # Import shared utilities

class Create(commands.Cog):
    """Cog for handling the 'create' command for DALL-E image generation."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger('twitch_bot.cogs.create')
        openai_api_key = os.getenv('OPENAI_API_KEY')
        self.nuuls_api_key = os.getenv('NUULS_API_KEY')  # Nuuls API key for image hosting

        if not openai_api_key:
            self.logger.error("OPENAI_API_KEY is not set in the environment variables.")
            raise ValueError("OPENAI_API_KEY is missing in the environment variables.")
        if not self.nuuls_api_key:
            self.logger.error("NUULS_API_KEY is not set in the environment variables.")
            raise ValueError("NUULS_API_KEY is missing.")

        # Instantiate the OpenAI client for DALL-E generation
        self.client = AsyncOpenAI(api_key=openai_api_key)

    async def upload_file(self, file_data: bytes, file_name: str) -> str:
        """Uploads a file (image) to i.nuuls.com and returns the hosted URL."""
        upload_endpoint = "https://i.nuuls.com/upload"
        try:
            async with aiohttp.ClientSession() as session:
                form = aiohttp.FormData()
                form.add_field('file', file_data, filename=file_name, content_type='multipart/form-data')

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

    async def download_image(self, url: str) -> bytes:
        """Downloads the image from the provided URL."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        return await resp.read()
                    else:
                        self.logger.error(f"Failed to download image from {url}. Status: {resp.status}")
                        return None
        except Exception as e:
            self.logger.error(f"Error downloading image: {e}", exc_info=True)
            return None

    async def generate_image(self, prompt: str, n: int = 1, size: str = "1024x1024") -> list:
        """Generates image(s) based on the prompt using DALL-E."""
        if "-wide" in prompt.lower():
            size = "1792x1024"
        elif "-tall" in prompt.lower():
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

    @commands.command(name='create')
    async def create_command(self, ctx: commands.Context, *, prompt: str = None):
        """Generates images using DALL-E based on user prompts."""
        if not prompt:
            await ctx.send(f"@{ctx.author.name}, please provide a prompt after the command.")
            return

        self.logger.info(f"Generating image for user '{ctx.author.name}' with prompt: {prompt}")
        image_urls = await self.generate_image(prompt)

        if image_urls:
            for url in image_urls:
                # Download the image from DALL-E URL
                image_data = await self.download_image(url)
                if image_data:
                    # Upload the downloaded image to i.nuuls
                    hosted_url = await self.upload_file(image_data, 'image.png')
                    if hosted_url:
                        await ctx.send(f"@{ctx.author.name}, here's your image: {hosted_url}")
                    else:
                        self.logger.warning("Failed to upload image.")
                        await ctx.send(f"@{ctx.author.name}, failed to upload the image.")
                else:
                    await ctx.send(f"@{ctx.author.name}, failed to download the image.")
        else:
            await ctx.send(f"@{ctx.author.name}, I'm unable to generate the image at this time.")

def setup(bot: commands.Bot):
    bot.add_cog(Create(bot))
