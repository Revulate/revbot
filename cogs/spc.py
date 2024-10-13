import os
import asyncio
import logging
import aiosqlite
import aiohttp
from twitchio.ext import commands
from rapidfuzz import process, fuzz
import time
from collections import OrderedDict


class Spc(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("twitch_bot.cogs.spc")
        self.logger.setLevel(logging.INFO)
        self.steam_api_key = os.getenv("API_STEAM_KEY")
        self.db_path = "steam_game.db"
        self.session = None
        self.bot.loop.create_task(self.initialize())
        self.game_cache = OrderedDict()
        self.player_count_cache = OrderedDict()
        self.reviews_cache = OrderedDict()
        self.game_details_cache = OrderedDict()
        self.MAX_CACHE_SIZE = 1000
        self.PLAYER_COUNT_CACHE_EXPIRY = 300  # 5 minutes
        self.REVIEWS_CACHE_EXPIRY = 3600  # 1 hour
        self.GAME_DETAILS_CACHE_EXPIRY = 86400  # 24 hours

    async def initialize(self):
        await self._setup_database()
        self.session = aiohttp.ClientSession()
        self.fetch_task = self.bot.loop.create_task(self.fetch_games_data_periodically())

    async def cog_unload(self):
        if self.fetch_task:
            self.fetch_task.cancel()
        if self.session:
            await self.session.close()
        self.logger.info("Spc cog unloaded and tasks canceled.")

    async def _setup_database(self):
        async with aiosqlite.connect(self.db_path) as db:
            # Create the table if it doesn't exist
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS Steam_Game (
                    ID INTEGER PRIMARY KEY,
                    Name TEXT NOT NULL
                )
            """
            )

            # Check if LastUpdated column exists, if not, add it
            cursor = await db.execute("PRAGMA table_info(Steam_Game)")
            columns = await cursor.fetchall()
            column_names = [column[1] for column in columns]

            if "LastUpdated" not in column_names:
                await db.execute("ALTER TABLE Steam_Game ADD COLUMN LastUpdated INTEGER")

            # Create index if it doesn't exist
            await db.execute("CREATE INDEX IF NOT EXISTS idx_name ON Steam_Game(Name)")
            await db.commit()
        self.logger.info("Steam_Game table, LastUpdated column, and index set up.")

    async def fetch_games_data_periodically(self):
        while True:
            try:
                await self.fetch_games_data()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error fetching Steam games data: {e}", exc_info=True)
            await asyncio.sleep(86400)  # Update daily

    async def fetch_games_data(self):
        self.logger.info("Fetching Steam games data...")
        url = "https://api.steampowered.com/ISteamApps/GetAppList/v2/"
        try:
            async with self.session.get(url, timeout=30) as response:
                if response.status != 200:
                    self.logger.error(f"Failed to fetch Steam app list: {response.status}")
                    return
                data = await response.json()
        except Exception as e:
            self.logger.error(f"Exception during Steam app list fetch: {e}", exc_info=True)
            return

        apps = data.get("applist", {}).get("apps", [])
        self.logger.info(f"Fetched {len(apps)} apps from Steam.")

        current_time = int(time.time())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("BEGIN TRANSACTION")
            try:
                # Check if LastUpdated column exists
                cursor = await db.execute("PRAGMA table_info(Steam_Game)")
                columns = await cursor.fetchall()
                has_last_updated = any(column[1] == "LastUpdated" for column in columns)

                for game in apps:
                    app_id, name = game.get("appid"), game.get("name")
                    if app_id and name:
                        if has_last_updated:
                            await db.execute(
                                "INSERT OR REPLACE INTO Steam_Game (ID, Name, LastUpdated) VALUES (?, ?, ?)",
                                (app_id, name, current_time),
                            )
                        else:
                            await db.execute(
                                "INSERT OR REPLACE INTO Steam_Game (ID, Name) VALUES (?, ?)", (app_id, name)
                            )
                await db.commit()
                self.logger.info("Steam games data updated successfully.")
            except Exception as e:
                await db.rollback()
                self.logger.error(f"Error updating the database: {e}", exc_info=True)

    @commands.command(name="spc", aliases=["sgp"])
    async def steam_game_players(self, ctx: commands.Context, *args):
        self.logger.info(f"Processing #spc command from {ctx.author.name}")

        if not self.steam_api_key and not args:
            await ctx.send(f"@{ctx.author.name}, Steam API key is not configured.")
            return

        gameID, skipReviews, gameName, channel_name = await self.parse_arguments(args, ctx)
        if gameID is None and gameName is None:
            return

        if not gameID and gameName:
            gameID = await self.find_game_id_by_name(gameName)
            if not gameID:
                await ctx.send(f"@{ctx.author.name}, no games found for your query: '{gameName}'.")
                return
            self.logger.debug(f"Game name provided. Found Game ID: {gameID}")

        player_count = await self.get_current_player_count(gameID)
        if player_count is None:
            await ctx.send(f"@{ctx.author.name}, could not retrieve player count for game ID {gameID}.")
            return

        reviews_string = "" if skipReviews else await self.get_game_reviews(gameID)
        game_details = await self.get_game_details(gameID)
        if not game_details:
            await ctx.send(f"@{ctx.author.name}, could not retrieve details for game ID {gameID}.")
            return

        reply = f"{game_details['name']} (by {', '.join(game_details['developers'])}) currently has **{player_count}** players in-game."
        if reviews_string:
            reply += f" {reviews_string}"

        await self.send_message(ctx, channel_name, reply)

    async def parse_arguments(self, args, ctx):
        if not args:
            await ctx.send(f"@{ctx.author.name}, please provide a game ID or name.")
            return None, None, None, None

        gameID = None
        skipReviews = False
        gameName = None
        channel_name = None

        first_arg = args[0]

        if first_arg.startswith("#"):
            channel_name = first_arg[1:].lower()
            args = args[1:]
            if not args:
                await ctx.send(f"@{ctx.author.name}, please provide a game ID or name after the channel.")
                return None, None, None, None
            first_arg = args[0]

        if first_arg.isdigit():
            gameID = int(first_arg)
            args = args[1:]
            if args:
                second_arg = args[0].lower()
                if second_arg in ["true", "1", "yes"]:
                    skipReviews = True
                    args = args[1:]
                if args:
                    gameName = " ".join(args)
        else:
            gameName = " ".join(args)

        if gameName and gameName.startswith("#"):
            parts = gameName.split(" ", 1)
            channel_name = parts[0][1:].lower()
            gameName = parts[1] if len(parts) > 1 else None

        if gameID and gameName:
            await ctx.send(f"@{ctx.author.name}, please provide either a game ID or a game name, not both.")
            return None, None, None, None

        return gameID, skipReviews, gameName, channel_name

    async def send_message(self, ctx, channel_name, reply):
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
            try:
                await ctx.send(reply)
                self.logger.info(f"Message sent in #{ctx.channel.name} by {ctx.author.name}.")
            except Exception as e:
                self.logger.error(f"Error sending message in #{ctx.channel.name}: {e}", exc_info=True)
                await ctx.send(f"@{ctx.author.name}, an error occurred while sending the message.")

    async def find_game_id_by_name(self, game_name: str) -> int:
        self.logger.info(f"Searching for game by name: {game_name}")
        if game_name.lower() in self.game_cache:
            return self.game_cache[game_name.lower()]

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

        if best_match and best_match[1] >= 80:
            matched_name = best_match[0]
            for game in games:
                if game[1] == matched_name:
                    self.game_cache[game_name.lower()] = game[0]
                    if len(self.game_cache) > self.MAX_CACHE_SIZE:
                        self.game_cache.popitem(last=False)
                    self.logger.debug(f"Fuzzy match found: '{matched_name}' with App ID {game[0]}")
                    return game[0]
        self.logger.info(f"No suitable fuzzy match found for game name: {game_name}")
        return None

    async def get_current_player_count(self, app_id: int) -> int:
        if app_id in self.player_count_cache:
            count, timestamp = self.player_count_cache[app_id]
            if time.time() - timestamp < self.PLAYER_COUNT_CACHE_EXPIRY:
                return count

        params = {"appid": app_id, "key": self.steam_api_key}
        try:
            async with self.session.get(
                "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/", params=params, timeout=10
            ) as response:
                if response.status != 200:
                    self.logger.error(f"Failed to fetch player count for App ID {app_id}: {response.status}")
                    return None
                data = await response.json()
                player_count = data.get("response", {}).get("player_count")
                self.player_count_cache[app_id] = (player_count, time.time())
                if len(self.player_count_cache) > self.MAX_CACHE_SIZE:
                    self.player_count_cache.popitem(last=False)
                self.logger.debug(f"Player count for App ID {app_id}: {player_count}")
                return player_count
        except Exception as e:
            self.logger.error(f"Exception during player count fetch: {e}", exc_info=True)
            return None

    async def get_game_reviews(self, app_id: int) -> str:
        if app_id in self.reviews_cache:
            reviews, timestamp = self.reviews_cache[app_id]
            if time.time() - timestamp < self.REVIEWS_CACHE_EXPIRY:
                return reviews

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
                    reviews = f"Rating: {review_score_desc} ({score_percentage}% positive)"
                else:
                    reviews = f"Rating: {review_score_desc}"

                self.reviews_cache[app_id] = (reviews, time.time())
                if len(self.reviews_cache) > self.MAX_CACHE_SIZE:
                    self.reviews_cache.popitem(last=False)
                return reviews
        except Exception as e:
            self.logger.error(f"Exception during reviews fetch: {e}", exc_info=True)
            return "Could not fetch reviews data."

    async def get_game_details(self, app_id: int) -> dict:
        if app_id in self.game_details_cache:
            details, timestamp = self.game_details_cache[app_id]
            if time.time() - timestamp < self.GAME_DETAILS_CACHE_EXPIRY:
                return details

        params = {"appids": app_id}
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
                details = {"name": game_data.get("name", "Unknown"), "developers": developers}

                self.game_details_cache[app_id] = (details, time.time())
                if len(self.game_details_cache) > self.MAX_CACHE_SIZE:
                    self.game_details_cache.popitem(last=False)
                return details
        except Exception as e:
            self.logger.error(f"Exception during game details fetch: {e}", exc_info=True)
            return None


def prepare(bot):
    bot.add_cog(Spc(bot))
