# cogs/spc.py

import os
import asyncio
import logging
import aiosqlite
import aiohttp
from twitchio.ext import commands
from rapidfuzz import process, fuzz  # For fuzzy search


class Spc(commands.Cog):
    """Cog for handling SteamDB interactions, including fetching game data and retrieving player counts."""

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("twitch_bot.cogs.spc")
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        if not self.logger.handlers:
            self.logger.addHandler(handler)

        self.steam_api_key = os.getenv("API_STEAM_KEY")
        if not self.steam_api_key:
            self.logger.warning("API_STEAM_KEY environment variable not set. Some features may be limited.")

        self.db_path = "steam_game.db"
        self.bot.loop.create_task(self._setup_database())

        # Initialize the HTTP session asynchronously
        self.session = None
        self.bot.loop.create_task(self.initialize_session())

        # Initialize the task for fetching game data
        self.fetch_task = self.bot.loop.create_task(self.fetch_games_data_periodically())

    async def initialize_session(self):
        """Asynchronously initialize the aiohttp ClientSession."""
        self.session = aiohttp.ClientSession()
        self.logger.info("Initialized aiohttp ClientSession.")

    def cog_unload(self):
        """Handle cog unload by canceling the fetch task and closing the HTTP session."""
        self.fetch_task.cancel()
        if self.session:
            asyncio.create_task(self.session.close())
            self.logger.info("Closed aiohttp ClientSession.")
        self.logger.info("Spc cog unloaded and fetch task canceled.")

    async def _setup_database(self):
        """Set up the Steam_Game table in the SQLite database."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS Steam_Game (
                        ID INTEGER PRIMARY KEY,
                        Name TEXT NOT NULL
                    )
                """
                )
                await db.commit()
            self.logger.info("Steam_Game table is set up.")
        except Exception as e:
            self.logger.error(f"Error setting up the database: {e}", exc_info=True)

    async def fetch_games_data_periodically(self):
        """Periodically fetches Steam games data every hour."""
        while True:
            try:
                await self.fetch_games_data()
            except asyncio.CancelledError:
                self.logger.info("Scheduled fetch task canceled.")
                break
            except Exception as e:
                self.logger.error(f"Error fetching Steam games data: {e}", exc_info=True)
            await asyncio.sleep(3600)  # Wait for 1 hour

    async def fetch_games_data(self):
        """Fetches the list of Steam games and updates the database."""
        self.logger.info("Fetching Steam games data...")

        # Corrected API endpoint to ISteamApps/GetAppList/v2/
        url = "https://api.steampowered.com/ISteamApps/GetAppList/v2/"
        params = {}

        try:
            async with self.session.get(url, params=params, timeout=10) as response:
                if response.status != 200:
                    self.logger.error(f"Failed to fetch Steam app list: {response.status}")
                    return
                data = await response.json()
        except Exception as e:
            self.logger.error(f"Exception during Steam app list fetch: {e}", exc_info=True)
            return

        apps = data.get("applist", {}).get("apps", [])
        self.logger.info(f"Fetched {len(apps)} apps from Steam.")

        try:
            async with aiosqlite.connect(self.db_path) as db:
                for game in apps:
                    app_id = game.get("appid")
                    name = game.get("name")

                    if not app_id or not name:
                        continue

                    try:
                        async with db.execute("SELECT 1 FROM Steam_Game WHERE ID = ?", (app_id,)) as cursor:
                            if await cursor.fetchone():
                                continue  # Game already exists

                        await db.execute("INSERT INTO Steam_Game (ID, Name) VALUES (?, ?)", (app_id, name))
                    except Exception as e:
                        self.logger.error(f"Error inserting game ID {app_id}: {e}", exc_info=True)
                await db.commit()
            self.logger.info("Steam games data updated successfully.")
        except Exception as e:
            self.logger.error(f"Error updating the database: {e}", exc_info=True)

    @commands.command(name="spc", aliases=["sgp"])
    async def steam_game_players(self, ctx: commands.Context, *args):
        """
        Searches for a Steam game and retrieves its current player count.

        Usage:
        - #spc [gameID] [skipReviews] [gameName]
        - #spc 105600
        - #spc 105600 True
        - #spc Terraria
        - #spc #vulpeshd Terraria  # Optional: specify channel
        """
        self.logger.info(f"Processing #spc command from {ctx.author.name}")

        if not self.steam_api_key and not args:
            await ctx.send(f"@{ctx.author.name}, Steam API key is not configured.")
            return

        # Initialize variables
        gameID, skipReviews, gameName, channel_name = await self.parse_arguments(args, ctx)
        if gameID is None and gameName is None:
            return

        # Fetch gameID if not provided
        if not gameID and gameName:
            gameID = await self.find_game_id_by_name(gameName)
            if not gameID:
                await ctx.send(f"@{ctx.author.name}, no games found for your query: '{gameName}'.")
                return
            self.logger.debug(f"Game name provided. Found Game ID: {gameID}")

        # Fetch current player count
        player_count = await self.get_current_player_count(gameID)
        if player_count is None:
            await ctx.send(f"@{ctx.author.name}, could not retrieve player count for game ID {gameID}.")
            return

        # Optionally fetch review scores
        reviews_string = ""
        if not skipReviews:
            reviews_string = await self.get_game_reviews(gameID)

        # Fetch game details
        game_details = await self.get_game_details(gameID)
        if not game_details:
            await ctx.send(f"@{ctx.author.name}, could not retrieve details for game ID {gameID}.")
            return

        # Format and send the response
        reply = f"{game_details['name']} (by {', '.join(game_details['developers'])}) currently has **{player_count}** players in-game."
        if reviews_string:
            reply += f" {reviews_string}"

        await self.send_message(ctx, channel_name, reply)

    async def parse_arguments(self, args, ctx):
        """Parse arguments provided to the spc command."""
        if not args:
            await ctx.send(f"@{ctx.author.name}, please provide a game ID or name.")
            return None, None, None, None

        gameID = None
        skipReviews = False
        gameName = None
        channel_name = None

        first_arg = args[0]

        if first_arg.startswith("#"):
            # Channel specification
            channel_name = first_arg[1:].lower()
            args = args[1:]  # Remove channel from args

            if not args:
                await ctx.send(f"@{ctx.author.name}, please provide a game ID or name after the channel.")
                return None, None, None, None

            first_arg = args[0]

        if first_arg.isdigit():
            # First argument is gameID
            gameID = int(first_arg)
            args = args[1:]

            if args:
                second_arg = args[0].lower()
                if second_arg in ["true", "1", "yes"]:
                    skipReviews = True
                    args = args[1:]
                # Remaining args are gameName
                if args:
                    gameName = " ".join(args)
        else:
            # First argument is gameName
            gameName = " ".join(args)

        # If gameName starts with '#', treat it as channel_name
        if gameName and gameName.startswith("#"):
            parts = gameName.split(" ", 1)
            channel_name = parts[0][1:].lower()
            gameName = parts[1] if len(parts) > 1 else None

        # Validate input
        if gameID and gameName:
            await ctx.send(f"@{ctx.author.name}, please provide either a game ID or a game name, not both.")
            return None, None, None, None

        return gameID, skipReviews, gameName, channel_name

    async def send_message(self, ctx, channel_name, reply):
        """Send a message to a specified channel or the current context."""
        if channel_name:
            connected_channels = [channel.name.lower() for channel in self.bot.connected_channels]
            if channel_name in connected_channels:
                target_channel = self.bot.get_channel(channel_name)
                if target_channel:
                    try:
                        await target_channel.send(reply)
                        await ctx.send(f"@{ctx.author.name}, message successfully sent to #{channel_name}.")
                        self.logger.info(f"Message sent to #{channel_name} by {ctx.author.name}.")
                    except Exception as e:
                        self.logger.error(f"Error sending message to #{channel_name}: {e}", exc_info=True)
                        await ctx.send(
                            f"@{ctx.author.name}, an error occurred while sending the message to #{channel_name}."
                        )
                else:
                    await ctx.send(f"@{ctx.author.name}, could not find channel #{channel_name}.")
                    self.logger.error(f"Channel object for #{channel_name} not found.")
            else:
                await ctx.send(f"@{ctx.author.name}, I am not connected to channel #{channel_name}.")
                self.logger.warning(f"Attempted to send to disconnected channel #{channel_name} by {ctx.author.name}.")
        else:
            # Send in the current channel
            try:
                await ctx.send(reply)
                self.logger.info(f"Message sent in #{ctx.channel.name} by {ctx.author.name}.")
            except Exception as e:
                self.logger.error(f"Error sending message in #{ctx.channel.name}: {e}", exc_info=True)
                await ctx.send(f"@{ctx.author.name}, an error occurred while sending the message.")

    async def find_game_id_by_name(self, game_name: str) -> int:
        """Find the Steam App ID by game name using fuzzy search."""
        self.logger.info(f"Searching for game by name: {game_name}")
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT ID, Name FROM Steam_Game WHERE Name LIKE ?", (f"%{game_name}%",)
                ) as cursor:
                    games = await cursor.fetchall()
        except Exception as e:
            self.logger.error(f"Error during game search: {e}", exc_info=True)
            return None

        if not games:
            return None

        game_names = [game[1] for game in games]
        best_match = process.extractOne(query=game_name, choices=game_names, scorer=fuzz.WRatio)

        if best_match and best_match[1] >= 80:  # Threshold can be adjusted
            matched_name = best_match[0]
            for game in games:
                if game[1] == matched_name:
                    self.logger.debug(f"Fuzzy match found: '{matched_name}' with App ID {game[0]}")
                    return game[0]
        self.logger.info(f"No suitable fuzzy match found for game name: {game_name}")
        return None

    async def get_current_player_count(self, app_id: int) -> int:
        """Retrieve the current number of players for a given Steam App ID."""
        params = {"appid": app_id}
        try:
            async with self.session.get(
                "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/", params=params, timeout=10
            ) as response:
                if response.status != 200:
                    self.logger.error(f"Failed to fetch player count for App ID {app_id}: {response.status}")
                    return None
                data = await response.json()
                player_count = data.get("response", {}).get("player_count")
                self.logger.debug(f"Player count for App ID {app_id}: {player_count}")
                return player_count
        except Exception as e:
            self.logger.error(f"Exception during player count fetch: {e}", exc_info=True)
            return None

    async def get_game_reviews(self, app_id: int) -> str:
        """Retrieve the review scores for a given Steam App ID."""
        url = f"https://store.steampowered.com/appreviews/{app_id}/"
        params = {"json": "1", "filter": "all", "language": "all"}
        try:
            async with self.session.get(url, params=params, timeout=10) as response:
                if response.status != 200:
                    self.logger.error(f"Failed to fetch reviews for App ID {app_id}: {response.status}")
                    return "Could not fetch reviews data."
                data = await response.json()
                summary = data.get("query_summary", {})
                total_reviews = summary.get("total_reviews", 0)
                total_positive = summary.get("total_positive", 0)
                review_score_desc = summary.get("review_score_desc", "No Reviews")

                if total_reviews > 0:
                    score_percentage = round((total_positive / total_reviews) * 100, 1)
                    return f"Rating: {review_score_desc} ({score_percentage}% positive)"
                else:
                    return f"Rating: {review_score_desc}"
        except Exception as e:
            self.logger.error(f"Exception during reviews fetch: {e}", exc_info=True)
            return "Could not fetch reviews data."

    async def get_game_details(self, app_id: int) -> dict:
        """Retrieve the details of a Steam game by App ID."""
        params = {"appids": app_id}  # Correct parameter name
        try:
            async with self.session.get(
                "https://store.steampowered.com/api/appdetails", params=params, timeout=10
            ) as response:
                if response.status != 200:
                    self.logger.error(f"Failed to fetch game details for App ID {app_id}: {response.status}")
                    return None
                data = await response.json()
                game_data = data.get(str(app_id), {}).get("data")
                if not game_data:
                    self.logger.error(f"No data found for App ID {app_id}.")
                    return None
                developers = game_data.get("developers", [])
                return {"name": game_data.get("name", "Unknown"), "developers": developers}
        except Exception as e:
            self.logger.error(f"Exception during game details fetch: {e}", exc_info=True)
            return None


def prepare(bot):
    bot.add_cog(Spc(bot))
