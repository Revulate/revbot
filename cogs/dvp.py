import asyncio
import aiosqlite
from twitchio.ext import commands
import os
from datetime import datetime, timezone, timedelta
from fuzzywuzzy import process, fuzz
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from playwright.async_api import async_playwright
from tenacity import retry, stop_after_attempt, wait_exponential
import re
from dotenv import load_dotenv

from twitch_helix_client import TwitchAPI
from logger import log_error, log_info, log_warning
from utils import is_valid_url


class DVP(commands.Cog):
    def __init__(self, bot):
        load_dotenv()
        self.bot = bot
        self.db_path = "vulpes_games.db"
        self.channel_name = "vulpeshd"
        self.update_scrape_task = None
        self.sheet_id = os.getenv("GOOGLE_SHEET_ID")
        self.creds_file = os.getenv("GOOGLE_CREDENTIALS_FILE")
        self.db_initialized = asyncio.Event()
        self.last_scrape_time = None
        self.browser = None

        if not self.sheet_id or not self.creds_file:
            raise ValueError("GOOGLE_SHEET_ID and GOOGLE_CREDENTIALS_FILE must be set in environment variables")

        client_id = os.getenv("TWITCH_CLIENT_ID")
        client_secret = os.getenv("TWITCH_CLIENT_SECRET")
        redirect_uri = os.getenv("TWITCH_REDIRECT_URI")
        if not client_id or not client_secret or not redirect_uri:
            raise ValueError(
                "TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET, and TWITCH_REDIRECT_URI must be set in environment variables"
            )
        self.twitch_api = TwitchAPI(client_id, client_secret, redirect_uri)

        self.abbreviation_mapping = {
            "ff7": "FINAL FANTASY VII REMAKE",
            "ff16": "FINAL FANTASY XVI",
            "ffxvi": "FINAL FANTASY XVI",
            "ff14": "FINAL FANTASY XIV",
            "rebirth": "FINAL FANTASY VII REBIRTH",
            "rdr2": "Red Dead Redemption 2",
            "er": "ELDEN RING",
            "ds3": "DARK SOULS III",
            "gow": "God of War",
            "gta": "Grand Theft Auto V",
            "gta5": "Grand Theft Auto V",
            "botw": "The Legend of Zelda: Breath of the Wild",
            "totk": "The Legend of Zelda: Tears of the Kingdom",
            "ac": "Assassin's Creed",
            "ac origins": "Assassin's Creed Origins",
            "ac odyssey": "Assassin's Creed Odyssey",
            "ffx": "FINAL FANTASY X",
            "bb": "Bloodborne",
            "tw3": "The Witcher 3: Wild Hunt",
            "witcher 3": "The Witcher 3: Wild Hunt",
            "boneworks": "BONEWORKS",
        }

        self.sheet_url = os.getenv("GOOGLE_SHEET_URL")
        if not self.sheet_url:
            self.sheet_url = f"https://docs.google.com/spreadsheets/d/{self.sheet_id}/edit?usp=sharing"

        self.bot.loop.create_task(self.initialize_cog())

    async def initialize_cog(self):
        log_info("DVP cog is initializing")
        await self.setup_database()
        await self.load_last_scrape_time()
        await self.initialize_data()
        self.update_scrape_task = asyncio.create_task(self.periodic_scrape_update())
        log_info("DVP cog initialized successfully")

    async def cog_unload(self):
        if self.update_scrape_task:
            self.update_scrape_task.cancel()
        if self.browser:
            await self.browser.close()

    async def setup_database(self):
        log_info(f"Setting up database at {self.db_path}")
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS games (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        time_played INTEGER NOT NULL,
                        last_played DATE NOT NULL
                    )
                """
                )
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                """
                )
                await db.commit()
            log_info("Database setup complete")
        except Exception as e:
            log_error(f"Error setting up database: {e}", exc_info=True)
            raise

    async def load_last_scrape_time(self):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT value FROM metadata WHERE key = 'last_scrape_time'") as cursor:
                result = await cursor.fetchone()
                if result:
                    try:
                        self.last_scrape_time = datetime.fromisoformat(result[0])
                        log_info(f"Last scrape time loaded: {self.last_scrape_time}")
                    except ValueError as ve:
                        log_error(f"Invalid datetime format in metadata: {result[0]}. Error: {ve}", exc_info=True)
                        self.last_scrape_time = None

    async def save_last_scrape_time(self):
        current_time = datetime.now(timezone.utc)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                ("last_scrape_time", current_time.isoformat()),
            )
            await db.commit()
        self.last_scrape_time = current_time
        log_info(f"Last scrape time saved: {self.last_scrape_time}")

    async def initialize_data(self):
        try:
            log_info("Initializing data")
            if not self.last_scrape_time or (datetime.now(timezone.utc) - self.last_scrape_time) > timedelta(days=7):
                log_info("Performing initial web scraping")
                await self.scrape_initial_data()
                await self.save_last_scrape_time()
            else:
                log_info("Skipping web scraping, using existing data")
            await self.update_initials_mapping()
            self.db_initialized.set()
            log_info("Data initialization completed successfully.")
        except Exception as e:
            log_error(f"Error initializing data: {e}", exc_info=True)
            self.db_initialized.set()

    async def scrape_initial_data(self):
        log_info("Initializing data from web scraping using Playwright...")
        try:
            async with async_playwright() as p:
                self.browser = await p.chromium.launch(headless=True)
                context = await self.browser.new_context()
                page = await context.new_page()

                await page.goto(f"https://twitchtracker.com/{self.channel_name}/games")
                await page.wait_for_selector("#games")

                await page.select_option('select[name="games_length"]', value="-1")
                await asyncio.sleep(5)

                rows = await page.query_selector_all("#games tbody tr")
                log_info(f"Found {len(rows)} rows in the games table.")

                async with aiosqlite.connect(self.db_path) as db:
                    for row in rows:
                        columns = await row.query_selector_all("td")
                        if len(columns) >= 7:
                            name = (await columns[1].inner_text()).strip()
                            time_played_str = (await columns[2].inner_text()).strip()
                            _, time_played = self.parse_time(time_played_str)
                            last_played_str = (await columns[6].inner_text()).strip()
                            try:
                                last_played = datetime.strptime(last_played_str, "%d/%b/%Y").date()
                            except ValueError as ve:
                                log_error(f"Error parsing date '{last_played_str}': {ve}", exc_info=True)
                                last_played = datetime.now(timezone.utc).date()
                            await db.execute(
                                """
                                INSERT INTO games (name, time_played, last_played)
                                VALUES (?, ?, ?)
                                ON CONFLICT(name) DO UPDATE SET
                                    time_played = excluded.time_played,
                                    last_played = excluded.last_played
                                """,
                                (name, time_played, last_played),
                            )
                    await db.commit()

                log_info("Initial data scraping completed and data inserted into the database.")
        except Exception as e:
            log_error(f"Error during data scraping: {e}", exc_info=True)
        finally:
            if self.browser:
                await self.browser.close()
                self.browser = None

    def parse_time(self, time_str):
        total_minutes = 0
        time_str = time_str.replace(",", "").strip().split("\n")[0].replace("%", "")
        try:
            if "." in time_str:
                hours = float(time_str)
                total_minutes = int(hours * 60)
            else:
                parts = time_str.split()
                i = 0
                while i < len(parts):
                    value_match = re.match(r"(\d+(\.\d+)?)", parts[i])
                    if not value_match:
                        log_error(f"Invalid numeric value in time string '{time_str}'")
                        break
                    value = float(value_match.group(1))
                    if i + 1 < len(parts):
                        unit = parts[i + 1].rstrip("s").lower()
                        i += 2
                    else:
                        unit = "hour"
                        i += 1
                    if unit == "day":
                        total_minutes += value * 24 * 60
                    elif unit == "hour":
                        total_minutes += value * 60
                    elif unit == "minute":
                        total_minutes += value
                    else:
                        log_error(f"Unknown time unit '{unit}' in time string '{time_str}'")
        except Exception as e:
            log_error(f"Error parsing time string '{time_str}': {e}", exc_info=True)

        return time_str, total_minutes

    def format_playtime(self, total_minutes):
        days, remaining_minutes = divmod(total_minutes, 24 * 60)
        hours, minutes = divmod(remaining_minutes, 60)

        if days > 0:
            total_hours = total_minutes / 60.0
            time_played = f"{int(days)}d {int(hours)}h {int(minutes)}m ({total_hours:.2f} hours)"
        elif hours > 0:
            time_played = f"{int(hours)}h {int(minutes)}m"
        else:
            time_played = f"{int(minutes)}m"
        return time_played

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def update_google_sheet(self):
        creds = Credentials.from_service_account_file(
            self.creds_file, scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        service = build("sheets", "v4", credentials=creds)

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT name, time_played, last_played FROM games WHERE name != 'Unknown' ORDER BY last_played DESC"
            ) as cursor:
                rows = await cursor.fetchall()

        headers = ["Game Image", "Game Name", "Time Played", "Last Played"]
        data = [headers]

        for row in rows:
            name, minutes, last_played = row
            game_image_url = await self.twitch_api.get_game_image_url(name)

            if game_image_url and not is_valid_url(game_image_url):
                log_warning(f"Invalid image URL for game '{name}': {game_image_url}")
                img_formula = ""
            else:
                img_formula = f'=IMAGE("{game_image_url}")' if game_image_url else ""

            time_played = self.format_playtime(minutes)

            try:
                last_played_date = datetime.strptime(str(last_played), "%Y-%m-%d")
                last_played_formatted = last_played_date.strftime("%B %d, %Y")
            except ValueError as ve:
                log_error(f"Error formatting last played date '{last_played}': {ve}", exc_info=True)
                last_played_formatted = str(last_played)

            data.append([img_formula, name, time_played, last_played_formatted])

        body = {"values": data}

        try:
            service.spreadsheets().values().clear(
                spreadsheetId=self.sheet_id,
                range="A3:D1000",
            ).execute()

            service.spreadsheets().values().update(
                spreadsheetId=self.sheet_id, range="A3", valueInputOption="USER_ENTERED", body=body
            ).execute()

            await self.apply_sheet_formatting(service, len(data))

            log_info("Google Sheet updated successfully.")
        except HttpError as error:
            log_error(f"An error occurred while updating the Google Sheet: {error}")
            raise

    async def apply_sheet_formatting(self, service, data_row_count):
        try:
            sheet_id = await self.get_sheet_id(service, self.sheet_id)

            requests = [
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": sheet_id,
                            "gridProperties": {"frozenRowCount": 3},
                        },
                        "fields": "gridProperties.frozenRowCount",
                    }
                },
                {
                    "repeatCell": {
                        "range": {"sheetId": sheet_id, "startRowIndex": 2, "endRowIndex": 3},
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0},
                                "textFormat": {
                                    "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                                    "bold": True,
                                },
                            }
                        },
                        "fields": "userEnteredFormat(backgroundColor,textFormat)",
                    }
                },
                {
                    "updateCells": {
                        "rows": [
                            {
                                "values": [
                                    {
                                        "userEnteredValue": {
                                            "formulaValue": f'=HYPERLINK("https://twitch.tv/{self.channel_name}", "VulpesHD")'
                                        },
                                        "userEnteredFormat": {"textFormat": {"bold": True, "fontSize": 14}},
                                    }
                                ]
                            }
                        ],
                        "fields": "userEnteredValue,userEnteredFormat.textFormat",
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 0,
                            "endRowIndex": 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": 1,
                        },
                    }
                },
            ]

            body = {"requests": requests}
            service.spreadsheets().batchUpdate(spreadsheetId=self.sheet_id, body=body).execute()

            log_info("Applied formatting to the Google Sheet.")
        except HttpError as e:
            log_error(f"An error occurred while applying formatting: {e}")
        except Exception as ex:
            log_error(f"Unexpected error during sheet formatting: {ex}", exc_info=True)

    async def get_sheet_id(self, service, spreadsheet_id):
        try:
            sheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            sheets = sheet_metadata.get("sheets", "")
            if not sheets:
                log_error(f"No sheets found in spreadsheet ID '{spreadsheet_id}'.")
                return 0
            for sheet in sheets:
                if sheet.get("properties", {}).get("title") == "Sheet1":
                    return sheet.get("properties", {}).get("sheetId", 0)
            sheet_id = sheets[0].get("properties", {}).get("sheetId", 0)
            return sheet_id
        except Exception as e:
            log_error(f"Error retrieving sheet ID: {e}", exc_info=True)
            return 0

    async def periodic_scrape_update(self):
        while True:
            try:
                log_info("Starting periodic web scraping update.")
                await self.scrape_initial_data()
                await self.save_last_scrape_time()
                await self.update_initials_mapping()
                await self.update_google_sheet()
                log_info("Periodic web scraping update completed.")
            except Exception as e:
                log_error(f"Error during periodic web scraping update: {e}", exc_info=True)
            await asyncio.sleep(86400)  # Run once every 24 hours

    async def update_initials_mapping(self):
        self.initials_mapping = {abbrev.lower(): game_name for abbrev, game_name in self.abbreviation_mapping.items()}
        log_info("Updated initials mapping")

    @commands.command(name="dvp")
    async def did_vulpes_play_it(self, ctx: commands.Context, *, game_name: str):
        log_info(f"dvp command called with game: {game_name}")
        await self.db_initialized.wait()
        try:
            game_name_normalized = game_name.strip().lower()
            log_info(f"Normalized game name: '{game_name_normalized}'")

            if game_name_normalized in self.abbreviation_mapping:
                game_name_to_search = self.abbreviation_mapping[game_name_normalized]
                log_info(f"Input '{game_name_normalized}' matched to abbreviation mapping '{game_name_to_search}'")
            else:
                async with aiosqlite.connect(self.db_path) as db:
                    async with db.execute("SELECT name FROM games") as cursor:
                        games = await cursor.fetchall()
                game_names = [game[0] for game in games]
                game_names_lower = [name.lower() for name in game_names]

                if game_name_normalized in game_names_lower:
                    index = game_names_lower.index(game_name_normalized)
                    game_name_to_search = game_names[index]
                    log_info(f"Exact match found: '{game_name_to_search}'")
                else:
                    matches = [
                        original_name
                        for original_name, lower_name in zip(game_names, game_names_lower)
                        if game_name_normalized in lower_name
                    ]
                    if matches:
                        game_name_to_search = matches[0]
                        log_info(f"Substring matched '{game_name_normalized}' to '{game_name_to_search}'")
                    else:
                        matches = process.extract(
                            game_name_normalized, game_names, scorer=fuzz.token_set_ratio, limit=3
                        )
                        log_info(f"Fuzzy matches: {matches}")
                        if matches and matches[0][1] >= 70:
                            game_name_to_search = matches[0][0]
                            log_info(f"Fuzzy matched '{game_name_normalized}' to '{game_name_to_search}'")
                        else:
                            log_warning(f"No matches found for '{game_name}' using fuzzy matching.")
                            await ctx.send(f"@{ctx.author.name}, no games found matching '{game_name}'.")
                            return

            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT time_played, last_played FROM games WHERE name = ?", (game_name_to_search,)
                ) as cursor:
                    result = await cursor.fetchone()

            if result:
                time_played, last_played = result
                formatted_time = self.format_playtime(time_played)
                try:
                    last_played_date = datetime.strptime(str(last_played), "%Y-%m-%d")
                    last_played_formatted = last_played_date.strftime("%B %d, %Y")
                except ValueError as ve:
                    log_error(f"Error formatting last played date '{last_played}': {ve}", exc_info=True)
                    last_played_formatted = str(last_played)
                await ctx.send(
                    f"@{ctx.author.name}, Vulpes played {game_name_to_search} for {formatted_time}. Last played on {last_played_formatted}."
                )
            else:
                await ctx.send(f"@{ctx.author.name}, couldn't find data for {game_name_to_search}.")
        except Exception as e:
            log_error(f"Error executing dvp command: {e}", exc_info=True)
            await ctx.send(
                f"@{ctx.author.name}, an error occurred while processing your request. Please try again later."
            )

    @commands.command(name="sheet")
    async def show_google_sheet(self, ctx: commands.Context):
        """Responds with the viewable URL to the Google Sheet."""
        await ctx.send(f"@{ctx.author.name}, you can view Vulpes's game stats here: {self.sheet_url}")

    async def log_total_playtime_for_games(self, game_names):
        async with aiosqlite.connect(self.db_path) as db:
            for game_name in game_names:
                async with db.execute("SELECT SUM(duration) FROM streams WHERE game_name = ?", (game_name,)) as cursor:
                    result = await cursor.fetchone()
                    total_duration = result[0] if result and result[0] else 0
                    total_minutes = total_duration // 60
                    log_info(f"Total playtime for {game_name}: {self.format_playtime(total_minutes)}")


def prepare(bot):
    bot.add_cog(DVP(bot))
