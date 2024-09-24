import random
from twitchio.ext import commands

class Roll(commands.Cog):
    """Cog for handling the 'roll' and 'dice' commands to simulate dice rolls."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="dice")
    async def dice_command(self, ctx: commands.Context, sides: int = 20, minimum: int = None):
        """
        Rolls a die with the given number of sides in a D&D-themed style. If a minimum value is provided, checks if the roll passes.
        
        Usage:
            #dice         -> rolls a 20-sided die by default
            #dice 6       -> rolls a 6-sided die
            #dice 6 2     -> rolls a 6-sided die and checks if the roll is 2 or higher
        """
        # Cap the dice size at 1000 sides for a condensed response
        sides = min(sides, 1000)
        
        # Perform the dice roll
        result = random.randint(1, sides)
        
        if minimum is None:
            # No minimum specified, just display the roll result
            await ctx.send(f"@{ctx.author.name} rolled d{sides} and got {result}!")
        else:
            # Roll check with minimum
            if result >= minimum:
                await ctx.send(f"@{ctx.author.name} rolled d{sides} and got {result}... vs {minimum}. Success!")
            else:
                await ctx.send(f"@{ctx.author.name} rolled d{sides} and got {result}... vs {minimum}. Failure!")

    @commands.command(name="roll")
    async def roll_command(self, ctx: commands.Context, sides: int = 100):
        """
        Simple roll command that just rolls the dice and shows the result.
        
        Usage:
            #roll         -> rolls a 100-sided die by default
            #roll 6       -> rolls a 6-sided die
        """
        # Cap the number of sides to 1000, and ensure at least 2 sides
        sides = min(max(sides, 2), 1000)

        # Perform the dice roll
        result = random.randint(1, sides)

        # Simple response mentioning the user
        await ctx.send(f"@{ctx.author.name} rolls {result} out of {sides}.")

def setup(bot: commands.Bot):
    bot.add_cog(Roll(bot))
