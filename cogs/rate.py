# rate.py
import random
import re
from twitchio.ext import commands
from logger import setup_logger  # Import the centralized logger
from utils import split_message  # Import the shared split_message function

class Rate(commands.Cog):
    """Cog for handling various rate-based commands like 'cute', 'gay', 'iq', etc.'"""

    def __init__(self, bot):
        self.bot = bot
        self.logger = setup_logger('twitch_bot.cogs.rate')  # Reuse the centralized logger

    def get_mentioned_user(self, ctx: commands.Context, mentioned_user: str = None):
        """Helper method to extract a mentioned user or default to the command author."""
        if mentioned_user:
            mentioned_user = mentioned_user.lstrip("@")
        else:
            mentioned_user = ctx.author.name
        return f"@{mentioned_user}"

    @commands.command(name="cute")
    async def cute_command(self, ctx: commands.Context, *, mentioned_user: str = None):
        """Returns a percentage of cuteness with a different response based on the result."""
        user = self.get_mentioned_user(ctx, mentioned_user)
        cute = random.randint(0, 100)
        response = f"{user} is {cute}% cute. {'MenheraCute' if cute >= 50 else 'SadgeCry'}"
        self.logger.info(f"Cute command result: {response}")
        await ctx.send(response)

    @commands.command(name="gay")
    async def gay_command(self, ctx: commands.Context, *, mentioned_user: str = None):
        """Returns a percentage of how gay the user is."""
        user = self.get_mentioned_user(ctx, mentioned_user)
        gay_percentage = random.randint(0, 100)
        response = f"{user} is {gay_percentage}% gay. {'Gayge' if gay_percentage > 50 else '📏'}"
        self.logger.info(f"Gay command result: {response}")
        await ctx.send(response)

    @commands.command(name="straight")
    async def straight_command(self, ctx: commands.Context, *, mentioned_user: str = None):
        """Returns a percentage of how straight the user is."""
        user = self.get_mentioned_user(ctx, mentioned_user)
        straight_percentage = random.randint(0, 100)
        response = f"{user} is {straight_percentage}% straight. {'📏' if straight_percentage > 50 else 'Hmm'}"
        self.logger.info(f"Straight command result: {response}")
        await ctx.send(response)

    @commands.command(name="myd", aliases=["pp", "kok"])
    async def myd_command(self, ctx: commands.Context, *, mentioned_user: str = None):
        """Returns the user's pp size in inches and converts it to feet if large enough."""
        user = self.get_mentioned_user(ctx, mentioned_user)
        length_inches = random.choices([random.randint(0, 11), random.randint(12, 24)], weights=[90, 10])[0]
        girth_inches = random.randint(1, 12)

        if length_inches >= 12:
            feet = length_inches // 12
            inches = length_inches % 12
            length_str = f"{feet}ft {inches}in"
        else:
            length_str = f"{length_inches}in"

        response = f"{user} 's pp is {length_str} long and has a {girth_inches}in girth. BillyApprove"
        self.logger.info(f"MYD command result: {response}")
        await ctx.send(response)

    @commands.command(name="rate")
    async def rate_command(self, ctx: commands.Context, *, mentioned_user: str = None):
        """Rates the user on a scale from 0 to 10."""
        user = self.get_mentioned_user(ctx, mentioned_user)
        rating = random.randint(0, 10)
        response = f"I would give {user} a {rating}/10. {'CHUG' if rating > 5 else 'Hmm'}"
        self.logger.info(f"Rate command result: {response}")
        await ctx.send(response)

    @commands.command(name="horny")
    async def horny_command(self, ctx: commands.Context, *, mentioned_user: str = None):
        """Returns how horny the user is."""
        user = self.get_mentioned_user(ctx, mentioned_user)
        horny_percentage = random.randint(0, 100)
        response = f"{user} is {horny_percentage}% horny right now. {'HORNY' if horny_percentage > 50 else 'Hmm'}"
        self.logger.info(f"Horny command result: {response}")
        await ctx.send(response)

    @commands.command(name="iq")
    async def iq_command(self, ctx: commands.Context, *, mentioned_user: str = None):
        """Returns a random IQ score and adds a comment based on the result."""
        user = self.get_mentioned_user(ctx, mentioned_user)
        iq = random.randint(0, 200)
        iq_description = "thoughtless" if iq <= 50 else "slowpoke" if iq <= 80 else "NPC" if iq <= 115 else "catNerd" if iq <= 199 else "BrainGalaxy"
        response = f"{user} has {iq} IQ. {iq_description}"
        self.logger.info(f"IQ command result: {response}")
        await ctx.send(response)

    @commands.command(name="sus")
    async def sus_command(self, ctx: commands.Context, *, mentioned_user: str = None):
        """Returns how sus the user is."""
        user = self.get_mentioned_user(ctx, mentioned_user)
        sus_percentage = random.randint(0, 100)
        response = f"{user} is {sus_percentage}% sus! {'SUSSY' if sus_percentage > 50 else 'Hmm'}"
        self.logger.info(f"Sus command result: {response}")
        await ctx.send(response)

    @commands.command(name='all')
    async def all_command(self, ctx: commands.Context, *, mentioned_user: str = None):
        """Runs all rate commands for the user and sends each result as a separate message."""
        user = self.get_mentioned_user(ctx, mentioned_user)
        self.logger.info(f"Running all rate commands for {user}")

        # Collect all responses
        messages = []

        cute = random.randint(0, 100)
        messages.append(f"{user} is {cute}% cute. {'MenheraCute' if cute >= 50 else 'SadgeCry'}")

        gay_percentage = random.randint(0, 100)
        messages.append(f"{user} is {gay_percentage}% gay. {'Gayge' if gay_percentage > 50 else '📏'}")

        straight_percentage = random.randint(0, 100)
        messages.append(f"{user} is {straight_percentage}% straight. {'📏' if straight_percentage > 50 else 'Hmm'}")

        length_inches = random.choices([random.randint(0, 11), random.randint(12, 24)], weights=[90, 10])[0]
        girth_inches = random.randint(1, 12)
        if length_inches >= 12:
            feet = length_inches // 12
            inches = length_inches % 12
            length_str = f"{feet}ft {inches}in"
        else:
            length_str = f"{length_inches}in"
        messages.append(f"{user} 's pp is {length_str} long and has a {girth_inches}in girth. BillyApprove")

        rating = random.randint(0, 10)
        messages.append(f"{user} is a {rating}/10. {'CHUG' if rating > 5 else 'Hmm'}")

        horny_percentage = random.randint(0, 100)
        messages.append(f"{user} is {horny_percentage}% horny right now. {'HORNY' if horny_percentage > 50 else 'Hmm'}")

        iq = random.randint(0, 200)
        iq_description = "thoughtless" if iq <= 50 else "slowpoke" if iq <= 80 else "NPC" if iq <= 115 else "catNerd" if iq <= 199 else "BrainGalaxy"
        messages.append(f"{user} has {iq} IQ. {iq_description}")

        sus_percentage = random.randint(0, 100)
        messages.append(f"{user} is {sus_percentage}% sus! {'SUSSY' if sus_percentage > 50 else 'Hmm'}")

        # Send each message separately
        self.logger.debug(f"Sending {len(messages)} message(s) for the #all command.")

        for msg in messages:
            try:
                await ctx.send(msg)
            except Exception as e:
                self.logger.error(f"Error sending message: {e}", exc_info=True)
                await ctx.send(f"{user}, an unexpected error occurred while sending the response.")

    @commands.command(name="ball")
    async def ball_command(self, ctx: commands.Context, *, mentioned_user: str = None):
        """Provides a brief summary of all rate commands in one message."""
        user = self.get_mentioned_user(ctx, mentioned_user)
        self.logger.info(f"Running brief summary rate commands for {user}")

        # Generate all the random percentages and values for each category
        cute = random.randint(0, 100)
        gay_percentage = random.randint(0, 100)
        straight_percentage = random.randint(0, 100)
        length_inches = random.choices([random.randint(0, 11), random.randint(12, 24)], weights=[90, 10])[0]
        girth_inches = random.randint(1, 12)
        rating = random.randint(0, 10)
        horny_percentage = random.randint(0, 100)
        iq = random.randint(0, 200)
        sus_percentage = random.randint(0, 100)

        # Format the pp size
        if length_inches >= 12:
            feet = length_inches // 12
            inches = length_inches % 12
            length_str = f"{feet}ft {inches}in"
        else:
            length_str = f"{length_inches}in"

        # Determine variations based on the result
        cute_response = 'MenheraCute' if cute >= 50 else 'SadgeCry'
        gay_response = 'Gayge' if gay_percentage > 50 else '📏'
        horny_response = 'HORNY' if horny_percentage > 50 else 'despair'
        sus_response = 'SUSSY' if sus_percentage > 50 else 'Hmm'
        iq_description = (
            "thoughtless" if iq <= 50 else
            "a slowpoke" if iq <= 80 else
            "an NPC" if iq <= 115 else
            "catNerd" if iq <= 199 else
            "BrainGalaxy"
        )
        rate_response = 'CHUG' if rating > 5 else 'Hmm'

        # Create a coherent summary with variations
        response = (
            f"{user} is {cute}% cute ({cute_response}), {gay_percentage}% gay ({gay_response}), "
            f"and {straight_percentage}% straight. "
            f"Their pp is {length_str} long with a {girth_inches}in girth. "
            f"I would rate them {rating}/10 ({rate_response}). "
            f"Right now, they are {horny_percentage}% horny ({horny_response}). "
            f"With an IQ of {iq}, they are {iq_description}. "
            f"They are also {sus_percentage}% sus ({sus_response})."
        )

        # Adjust max_length to account for any prefixes or formatting
        max_length = 500  # Twitch's maximum message length

        # Use the split_message function to split the message appropriately
        messages_to_send = split_message(response, max_length=max_length)

        self.logger.debug(f"Sending {len(messages_to_send)} message(s) for the #ball command.")

        for msg in messages_to_send:
            try:
                await ctx.send(msg)
            except Exception as e:
                self.logger.error(f"Error sending message: {e}", exc_info=True)
                await ctx.send(f"{user}, an unexpected error occurred while sending the response.")

def prepare(bot):
    bot.add_cog(Rate(bot))
