import asyncio
import aiosqlite
from twitchio.ext import commands
import os
import aiohttp
from datetime import datetime, timezone
import logging
from fuzzywuzzy import process, fuzz
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import re
from playwright.async_api import async_playwright


class DVP(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "vulpes_games.db"
        self.channel_name = "vulpeshd"
        self.client_id = os.getenv("TWITCH_CLIENT_ID")
        self.client_secret = os.getenv("TWITCH_CLIENT_SECRET")
        self.logger = bot.logger.getChild("dvp")
        self.logger.setLevel(logging.DEBUG)
        self.update_task = None
        self.update_recent_games_task = None
        self.sheet_id = os.getenv("GOOGLE_SHEET_ID")
        self.creds_file = os.getenv("GOOGLE_CREDENTIALS_FILE")
        self.db_initialized = asyncio.Event()

        if not self.sheet_id:
            raise ValueError("GOOGLE_SHEET_ID is not set in the environment variables")
        if not self.creds_file:
            raise ValueError("GOOGLE_CREDENTIALS_FILE is not set in the environment variables")

        # Predefined abbreviations and aliases
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
            # Add more as needed
        }

        self.sheet_url = os.getenv("GOOGLE_SHEET_URL")
        if not self.sheet_url:
            self.sheet_url = f"https://docs.google.com/spreadsheets/d/{self.sheet_id}/edit?usp=sharing"

        self.bot.loop.create_task(self.initialize_cog())

    async def initialize_cog(self):
        self.logger.info("DVP cog is initializing")
        await self.setup_database()
        await self.initialize_data()
        self.update_task = self.bot.loop.create_task(self.periodic_update())
        self.update_recent_games_task = self.bot.loop.create_task(self.periodic_recent_games_update())
        self.logger.info("DVP cog initialized successfully")

    async def cog_unload(self):
        if self.update_task:
            self.update_task.cancel()
        if self.update_recent_games_task:
            self.update_recent_games_task.cancel()

    async def setup_database(self):
        self.logger.info(f"Setting up database at {self.db_path}")
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
                # Add a new table to store stream data
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS streams (
                        id TEXT PRIMARY KEY,
                        game_id TEXT,
                        game_name TEXT,
                        started_at TEXT,
                        duration INTEGER
                    )
                    """
                )
                await db.commit()
            self.logger.info("Database setup complete")
        except Exception as e:
            self.logger.error(f"Error setting up database: {e}", exc_info=True)
            raise

    async def initialize_data(self):
        try:
            self.logger.info("Initializing data from web scraping.")
            # First, scrape initial historical data
            await self.scrape_initial_data()
            # Then, fetch recent videos from Twitch API
            await self.fetch_recent_videos()
            await self.update_game_playtime()
            await self.update_initials_mapping()
            self.db_initialized.set()
            self.logger.info("Data initialization completed successfully.")
        except Exception as e:
            self.logger.error(f"Error initializing data: {e}", exc_info=True)
            self.db_initialized.set()

    async def scrape_initial_data(self):
        self.logger.info("Initializing data from web scraping using Playwright...")
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                page = await context.new_page()

                await page.goto(f"https://twitchtracker.com/{self.channel_name}/games")
                await page.wait_for_selector("#games")

                await page.select_option('select[name="games_length"]', value="-1")
                await asyncio.sleep(5)

                rows = await page.query_selector_all("#games tbody tr")
                self.logger.info(f"Found {len(rows)} rows in the games table.")

                async with aiosqlite.connect(self.db_path) as db:
                    for row in rows:
                        columns = await row.query_selector_all("td")
                        if len(columns) >= 7:
                            name = (await columns[1].inner_text()).strip()

                            time_played_element = await columns[2].query_selector("span")
                            if time_played_element:
                                time_played_str = (await time_played_element.inner_text()).strip()
                            else:
                                time_played_str = (await columns[2].inner_text()).strip()
                            self.logger.debug(f"Scraped time_played_str for '{name}': '{time_played_str}'")
                            time_played_str, time_played = self.parse_time(time_played_str)

                            last_played_str = (await columns[6].inner_text()).strip()
                            last_played = datetime.strptime(last_played_str, "%d/%b/%Y").date()
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

                await browser.close()
                self.logger.info("Initial data scraping completed and data inserted into the database.")
            await self.update_initials_mapping()
        except Exception as e:
            self.logger.error(f"Error during data scraping: {e}", exc_info=True)

    async def fetch_recent_videos(self):
        user_id = await self.get_user_id(self.channel_name)
        url = "https://api.twitch.tv/helix/videos"
        params = {"user_id": user_id, "first": 100, "type": "archive"}  # 'type': 'archive' fetches past broadcasts

        headers = {"Client-ID": self.client_id, "Authorization": f"Bearer {self.bot.twitch_api.oauth_token}"}

        async with aiohttp.ClientSession() as session:
            while True:
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        await self.process_video_data(data["data"])
                        # Handle pagination
                        if "pagination" in data and "cursor" in data["pagination"]:
                            params["after"] = data["pagination"]["cursor"]
                        else:
                            break
                    else:
                        self.logger.error(f"Failed to fetch recent videos: {response.status}")
                        break

    async def process_video_data(self, videos):
        async with aiosqlite.connect(self.db_path) as db:
            # Clear the streams table to prevent cumulative addition
            await db.execute("DELETE FROM streams")
            await db.commit()

            for video in videos:
                video_id = video["id"]
                game_name = video.get("game_name")
                if not game_name or game_name.lower() == "unknown":
                    continue  # Skip videos without a valid game name

                game_id = video.get("game_id", "")
                created_at = video["created_at"]
                duration_str = video["duration"]  # e.g., '2h15m42s'
                duration = self.parse_duration(duration_str)  # Convert to seconds

                await db.execute(
                    """
                    INSERT OR REPLACE INTO streams 
                    (id, game_id, game_name, started_at, duration) 
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (video_id, game_id, game_name, created_at, duration),
                )
            await db.commit()

    def parse_duration(self, duration_str):
        total_seconds = 0
        matches = re.findall(r"(\d+)([hms])", duration_str)
        for value, unit in matches:
            if unit == "h":
                total_seconds += int(value) * 3600
            elif unit == "m":
                total_seconds += int(value) * 60
            elif unit == "s":
                total_seconds += int(value)
        return total_seconds

    def generate_initials(self, title):
        title_cleaned = re.sub(r"[^A-Za-z0-9 ]+", "", title)
        words = title_cleaned.strip().split()
        initials_list = []
        for word in words:
            word_upper = word.upper()
            if self.is_roman_numeral(word_upper):
                numeral = self.roman_to_int(word_upper)
                initials_list.append(numeral)
            elif word.isdigit():
                initials_list.append(word)
            else:
                initials_list.append(word[0].upper())
        initials = "".join(initials_list)
        return initials.lower()

    def is_roman_numeral(self, s):
        return bool(re.fullmatch(r"M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})", s.upper()))

    def roman_to_int(self, s):
        roman_dict = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
        s = s.upper()
        total = 0
        prev_value = 0
        for char in reversed(s):
            value = roman_dict.get(char, 0)
            if value < prev_value:
                total -= value
            else:
                total += value
                prev_value = value
        return str(total)

    def parse_time(self, time_str):
        total_minutes = 0
        time_str = time_str.replace(",", "").strip()
        try:
            if "." in time_str:
                hours = float(time_str)
                total_minutes = int(hours * 60)
            else:
                parts = time_str.split()
                i = 0
                while i < len(parts):
                    value = float(parts[i])
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
                        self.logger.error(f"Unknown time unit '{unit}' in time string '{time_str}'")
        except Exception as e:
            self.logger.error(f"Error parsing time string '{time_str}': {e}", exc_info=True)

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

    async def get_channel_games(self):
        user_id = await self.get_user_id(self.channel_name)
        url = f"https://api.twitch.tv/helix/channels?broadcaster_id={user_id}"
        headers = {"Client-ID": self.client_id, "Authorization": f"Bearer {self.bot.twitch_api.oauth_token}"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return data["data"][0]["game_name"] if data["data"] else None
                else:
                    self.logger.error(f"Failed to fetch channel info: {response.status}")
                    return None

    async def get_user_id(self, username):
        users = await self.bot.fetch_users(names=[username])
        return users[0].id if users else None

    async def update_game_data(self, game_name, time_played):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO games (name, time_played, last_played)
                VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    time_played = time_played + excluded.time_played,
                    last_played = excluded.last_played
            """,
                (game_name, time_played, datetime.now(timezone.utc).date()),
            )
            await db.commit()

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

        # Prepare data for the sheet
        headers = ["Game Image", "Game Name", "Time Played", "Last Played"]
        data = [headers]

        for row in rows:
            name, minutes, last_played = row
            game_image_url = await self.get_game_image_url(name)  # Fetch the image URL

            # Format the time played into days, hours, minutes
            time_played = self.format_playtime(minutes)

            # Format the last played date
            last_played_date = datetime.strptime(str(last_played), "%Y-%m-%d")
            last_played_formatted = last_played_date.strftime("%B %d, %Y")

            # Prepare the image formula
            img_formula = f'=IMAGE("{game_image_url}")' if game_image_url else ""

            data.append([img_formula, name, time_played, last_played_formatted])

        # Update the data starting from cell A3
        body = {"values": data}

        try:
            # Clear existing data from A3 onwards
            service.spreadsheets().values().clear(
                spreadsheetId=self.sheet_id,
                range="A3:D1000",  # Adjust the end row as needed
            ).execute()

            # Write the data
            service.spreadsheets().values().update(
                spreadsheetId=self.sheet_id, range="A3", valueInputOption="USER_ENTERED", body=body
            ).execute()

            # Apply the header and formatting
            await self.apply_sheet_formatting(service, len(data))

            self.logger.info("Google Sheet updated successfully.")
        except HttpError as error:
            self.logger.error(f"An error occurred while updating the Google Sheet: {error}")

    async def get_game_image_url(self, game_name):
        try:
            url = "https://api.twitch.tv/helix/games"
            headers = {"Client-ID": self.client_id, "Authorization": f"Bearer {self.bot.twitch_api.oauth_token}"}
            params = {"name": game_name}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data["data"]:
                            box_art_url = data["data"][0]["box_art_url"]
                            # Replace placeholder dimensions with actual values
                            return box_art_url.replace("{width}", "285").replace("{height}", "380")
            self.logger.warning(f"No image found for game: {game_name}")
        except Exception as e:
            self.logger.error(f"Error fetching image URL for {game_name}: {e}", exc_info=True)
        return ""

    async def apply_sheet_formatting(self, service, data_row_count):
        try:
            sheet_id = await self.get_sheet_id(service, self.sheet_id)

            requests = []

            # Merge cells A1:D1 and set the value with hyperlink
            requests.append(
                {
                    "mergeCells": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 0,
                            "endRowIndex": 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": 4,
                        },
                        "mergeType": "MERGE_ALL",
                    }
                }
            )

            # Set the value of merged cells A1:D1 with hyperlink
            requests.append(
                {
                    "updateCells": {
                        "rows": [
                            {
                                "values": [
                                    {
                                        "userEnteredValue": {
                                            "formulaValue": '=HYPERLINK("https://twitch.tv/VulpesHD", "VulpesHD")'
                                        },
                                        "userEnteredFormat": {
                                            "horizontalAlignment": "CENTER",
                                            "textFormat": {"fontSize": 24, "bold": True},
                                        },
                                    }
                                ]
                            }
                        ],
                        "fields": "userEnteredValue,userEnteredFormat",
                        "start": {"sheetId": sheet_id, "rowIndex": 0, "columnIndex": 0},
                    }
                }
            )

            # Merge cells A2:D2 and set the "Last Updated" text
            current_date = datetime.now().strftime("%B %d, %Y %H:%M:%S")
            requests.append(
                {
                    "mergeCells": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": 2,
                            "startColumnIndex": 0,
                            "endColumnIndex": 4,
                        },
                        "mergeType": "MERGE_ALL",
                    }
                }
            )

            # Set the value of merged cells A2:D2
            requests.append(
                {
                    "updateCells": {
                        "rows": [
                            {
                                "values": [
                                    {
                                        "userEnteredValue": {"stringValue": f"Last Updated: {current_date}"},
                                        "userEnteredFormat": {
                                            "horizontalAlignment": "CENTER",
                                            "textFormat": {"fontSize": 12, "italic": True},
                                        },
                                    }
                                ]
                            }
                        ],
                        "fields": "userEnteredValue,userEnteredFormat",
                        "start": {"sheetId": sheet_id, "rowIndex": 1, "columnIndex": 0},
                    }
                }
            )

            # Adjust row heights for data rows
            requests.append(
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "startIndex": 3,  # Data starts from row index 3 (Row 4)
                            "endIndex": 3 + data_row_count - 1,  # Adjust based on data length
                        },
                        "properties": {"pixelSize": 147},
                        "fields": "pixelSize",
                    }
                }
            )

            # Resize columns A-D
            column_sizes = [110, 287, 255, 198]
            for idx, size in enumerate(column_sizes):
                requests.append(
                    {
                        "updateDimensionProperties": {
                            "range": {
                                "sheetId": sheet_id,
                                "dimension": "COLUMNS",
                                "startIndex": idx,
                                "endIndex": idx + 1,
                            },
                            "properties": {"pixelSize": size},
                            "fields": "pixelSize",
                        }
                    }
                )

            # Apply date formatting to "Last Played" column (Column D)
            requests.append(
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 3,  # Data starts from row index 3
                            "endRowIndex": 3 + data_row_count - 1,
                            "startColumnIndex": 3,  # Column D
                            "endColumnIndex": 4,
                        },
                        "cell": {"userEnteredFormat": {"numberFormat": {"type": "DATE", "pattern": "MMMM dd, yyyy"}}},
                        "fields": "userEnteredFormat.numberFormat",
                    }
                }
            )

            # Center align headers and make them bold
            requests.append(
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 2,  # Headers are in row index 2 (Row 3)
                            "endRowIndex": 3,
                            "startColumnIndex": 0,
                            "endColumnIndex": 4,
                        },
                        "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER", "textFormat": {"bold": True}}},
                        "fields": "userEnteredFormat(horizontalAlignment,textFormat)",
                    }
                }
            )

            # Center align data cells
            requests.append(
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 3,
                            "endRowIndex": 3 + data_row_count - 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": 4,
                        },
                        "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER"}},
                        "fields": "userEnteredFormat.horizontalAlignment",
                    }
                }
            )

            # Send the batch update
            body = {"requests": requests}
            service.spreadsheets().batchUpdate(spreadsheetId=self.sheet_id, body=body).execute()

            self.logger.info("Applied formatting to the Google Sheet.")
        except HttpError as e:
            self.logger.error(f"An error occurred while applying formatting: {e}")

    async def get_sheet_id(self, service, spreadsheet_id):
        try:
            sheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            sheets = sheet_metadata.get("sheets", "")
            sheet_id = sheets[0].get("properties", {}).get("sheetId", 0)
            return sheet_id
        except Exception as e:
            self.logger.error(f"Error retrieving sheet ID: {e}", exc_info=True)
            return 0

    async def periodic_update(self):
        while True:
            try:
                current_game = await self.get_channel_games()
                if current_game:
                    await self.update_game_data(current_game, 5)  # Update every 5 minutes
            except Exception as e:
                self.logger.error(f"Error during periodic update: {e}", exc_info=True)
            await asyncio.sleep(300)  # Sleep for 5 minutes

    async def periodic_recent_games_update(self):
        while True:
            try:
                await self.fetch_recent_videos()
                await self.update_game_playtime()
                await self.update_google_sheet()
            except Exception as e:
                self.logger.error(f"Error during periodic recent games update: {e}", exc_info=True)
            await asyncio.sleep(86400)  # Update daily

    async def update_game_playtime(self):
        async with aiosqlite.connect(self.db_path) as db:
            # Sum up the durations for each game
            async with db.execute(
                """
                SELECT game_name, SUM(duration)
                FROM streams
                GROUP BY game_name
            """
            ) as cursor:
                game_playtimes = await cursor.fetchall()

            for game_name, total_duration in game_playtimes:
                # Convert total_duration from seconds to minutes
                total_minutes = total_duration // 60
                last_played = datetime.now(timezone.utc).date()
                await db.execute(
                    """
                    INSERT INTO games (name, time_played, last_played)
                    VALUES (?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        time_played = excluded.time_played,
                        last_played = excluded.last_played
                    """,
                    (game_name, total_minutes, last_played),
                )
            await db.commit()

    async def update_initials_mapping(self):
        # Use only predefined abbreviations
        self.initials_mapping = {}
        for abbrev, game_name in self.abbreviation_mapping.items():
            self.initials_mapping[abbrev.lower()] = game_name
            self.logger.debug(f"Updated initials mapping: '{abbrev.lower()}' for game '{game_name}'")

    @commands.command(name="dvp")
    async def did_vulpes_play_it(self, ctx: commands.Context, *, game_name: str):
        self.logger.info(f"dvp command called with game: {game_name}")
        await self.db_initialized.wait()  # Wait for the database to be initialized
        try:
            # Normalize the input
            game_name_normalized = game_name.strip().lower()
            self.logger.debug(f"Normalized game name: '{game_name_normalized}'")

            # Check if the input matches any known abbreviations
            if game_name_normalized in self.abbreviation_mapping:
                game_name_to_search = self.abbreviation_mapping[game_name_normalized]
                self.logger.debug(
                    f"Input '{game_name_normalized}' matched to abbreviation mapping '{game_name_to_search}'"
                )
            else:
                # Fetch game names from the database
                async with aiosqlite.connect(self.db_path) as db:
                    async with db.execute("SELECT name FROM games") as cursor:
                        games = await cursor.fetchall()
                game_names = [game[0] for game in games]

                # Convert all game names to lowercase for matching
                game_names_lower = [name.lower() for name in game_names]

                # Check for exact matches
                if game_name_normalized in game_names_lower:
                    index = game_names_lower.index(game_name_normalized)
                    game_name_to_search = game_names[index]
                    self.logger.debug(f"Exact match found: '{game_name_to_search}'")
                else:
                    # Check for substring matches
                    matches = [
                        original_name
                        for original_name, lower_name in zip(game_names, game_names_lower)
                        if game_name_normalized in lower_name
                    ]
                    if matches:
                        game_name_to_search = matches[0]  # Choose the first match
                        self.logger.debug(f"Substring matched '{game_name_normalized}' to '{game_name_to_search}'")
                    else:
                        # Proceed with enhanced fuzzy matching
                        matches = process.extract(
                            game_name_normalized, game_names, scorer=fuzz.token_set_ratio, limit=3
                        )
                        self.logger.debug(f"Fuzzy matches: {matches}")
                        if matches and matches[0][1] >= 70:
                            game_name_to_search = matches[0][0]
                            self.logger.debug(f"Fuzzy matched '{game_name_normalized}' to '{game_name_to_search}'")
                        else:
                            self.logger.warning(f"No matches found for '{game_name}' using fuzzy matching.")
                            await ctx.send(f"@{ctx.author.name}, no games found matching '{game_name}'.")
                            return

            # Fetch game data and send response
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT time_played, last_played FROM games WHERE name = ?", (game_name_to_search,)
                ) as cursor:
                    result = await cursor.fetchone()

            if result:
                time_played, last_played = result
                formatted_time = self.format_playtime(time_played)
                last_played_formatted = datetime.strptime(str(last_played), "%Y-%m-%d").strftime("%B %d, %Y")
                await ctx.send(
                    f"@{ctx.author.name}, Vulpes played {game_name_to_search} for {formatted_time}. Last played on {last_played_formatted}."
                )
            else:
                await ctx.send(f"@{ctx.author.name}, couldn't find data for {game_name_to_search}.")
        except Exception as e:
            self.logger.error(f"Error executing dvp command: {e}", exc_info=True)
            await ctx.send(
                f"@{ctx.author.name}, an error occurred while processing your request. Please try again later."
            )

    @commands.command(name="sheet")
    async def show_google_sheet(self, ctx: commands.Context):
        """Responds with the viewable URL to the Google Sheet."""
        await ctx.send(f"@{ctx.author.name}, you can view Vulpes's game stats here: {self.sheet_url}")


def prepare(bot):
    bot.add_cog(DVP(bot))
