import asyncio
import aiosqlite
from twitchio.ext import commands
import os
from dotenv import load_dotenv
import aiohttp
from datetime import datetime, timezone, timedelta
import logging
from fuzzywuzzy import process
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from playwright.async_api import async_playwright
import re
from unidecode import unidecode

load_dotenv()


class DVP(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "vulpes_games.db"
        self.channel_name = "vulpeshd"
        self.client_id = os.getenv("TWITCH_CLIENT_ID")
        self.client_secret = os.getenv("TWITCH_CLIENT_SECRET")
        self.logger = bot.logger.getChild("dvp")
        self.logger.setLevel(logging.DEBUG)  # Set logger to DEBUG level
        self.update_task = None
        self.update_recent_games_task = None  # New task for recent games update
        self.sheet_id = os.getenv("GOOGLE_SHEET_ID")
        self.creds_file = os.getenv("GOOGLE_CREDENTIALS_FILE")
        self.db_initialized = asyncio.Event()

        # Validate environment variables
        if not self.sheet_id:
            raise ValueError("GOOGLE_SHEET_ID is not set in the environment variables")
        if not self.creds_file:
            raise ValueError("GOOGLE_CREDENTIALS_FILE is not set in the environment variables")

        # Add known abbreviations
        self.abbreviation_mapping = {
            "ff7": "FINAL FANTASY VII REMAKE",
            "ff16": "FINAL FANTASY XVI",
            "ffxvi": "FINAL FANTASY XVI",
            "rdr2": "Red Dead Redemption 2",
            "er": "ELDEN RING",
            "ds3": "DARK SOULS III",
            "gow": "God of War",
            # Add more known abbreviations as needed
        }

        # Set the sheet URL
        self.sheet_url = os.getenv("GOOGLE_SHEET_URL")
        if not self.sheet_url:
            # Construct the URL using the sheet ID
            self.sheet_url = f"https://docs.google.com/spreadsheets/d/{self.sheet_id}/edit?usp=sharing"

        # Start the initialization
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
                await db.commit()
            self.logger.info("Database setup complete")
        except Exception as e:
            self.logger.error(f"Error setting up database: {e}", exc_info=True)
            raise

    async def initialize_data(self):
        try:
            self.logger.info("Starting data initialization.")
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("SELECT name FROM games") as cursor:
                    games = await cursor.fetchall()
            if not games:
                self.logger.info("No data found in the database. Starting scraping.")
                await self.scrape_initial_data()
                # Fetch the game names again after scraping
                async with aiosqlite.connect(self.db_path) as db:
                    async with db.execute("SELECT name FROM games") as cursor:
                        games = await cursor.fetchall()
            else:
                self.logger.info("Data already exists. Skipping scraping.")

            # Generate initials mapping
            self.initials_mapping = {}
            for game in games:
                name = game[0]
                initials = self.generate_initials(name)
                self.initials_mapping[initials.lower()] = name
                self.logger.debug(f"Generated initials '{initials.lower()}' for game '{name}'")

            self.db_initialized.set()
            self.logger.info("Data initialization completed successfully.")
        except Exception as e:
            self.logger.error(f"Error initializing data: {e}", exc_info=True)
            self.db_initialized.set()  # Ensure the event is set to prevent hanging

    async def scrape_initial_data(self):
        self.logger.info("Initializing data from web scraping using Playwright...")
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                page = await context.new_page()

                await page.goto(f"https://twitchtracker.com/{self.channel_name}/games")
                await page.wait_for_selector("#games")

                # Select "All" from the dropdown to show all games
                await page.select_option('select[name="games_length"]', value="-1")
                await asyncio.sleep(5)  # Wait for table to update

                # Extract data from the table
                rows = await page.query_selector_all("#games tbody tr")
                self.logger.info(f"Found {len(rows)} rows in the games table.")

                async with aiosqlite.connect(self.db_path) as db:
                    for row in rows:
                        columns = await row.query_selector_all("td")
                        if len(columns) >= 7:
                            name = (await columns[1].inner_text()).strip()

                            # Get the 'span' within the time played column
                            time_played_element = await columns[2].query_selector("span")
                            if time_played_element:
                                time_played_str = (await time_played_element.inner_text()).strip()
                            else:
                                time_played_str = (await columns[2].inner_text()).strip()
                            self.logger.debug(f"Scraped time_played_str for '{name}': '{time_played_str}'")
                            time_played = self.parse_time(time_played_str)

                            last_played_str = (await columns[6].inner_text()).strip()
                            last_played = datetime.strptime(last_played_str, "%d/%b/%Y").date()
                            await db.execute(
                                """
                                INSERT INTO games (name, time_played, last_played)
                                VALUES (?, ?, ?)
                            """,
                                (name, time_played, last_played),
                            )
                    await db.commit()

                await browser.close()
                self.logger.info("Initial data scraping completed and data inserted into the database.")
        except Exception as e:
            self.logger.error(f"Error during data scraping: {e}", exc_info=True)

    async def update_recent_games(self):
        self.logger.info("Updating recent games data from web scraping using Playwright...")
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                page = await context.new_page()

                await page.goto(f"https://twitchtracker.com/{self.channel_name}/games")
                await page.wait_for_selector("#games")

                # Select "5" from the dropdown to show only 5 games
                await page.select_option('select[name="games_length"]', value="5")
                await asyncio.sleep(5)  # Wait for table to update

                # Extract data from the table
                rows = await page.query_selector_all("#games tbody tr")
                self.logger.info(f"Found {len(rows)} rows in the games table for recent update.")

                async with aiosqlite.connect(self.db_path) as db:
                    for row in rows:
                        columns = await row.query_selector_all("td")
                        if len(columns) >= 7:
                            name = (await columns[1].inner_text()).strip()

                            # Get the 'span' within the time played column
                            time_played_element = await columns[2].query_selector("span")
                            if time_played_element:
                                time_played_str = (await time_played_element.inner_text()).strip()
                            else:
                                time_played_str = (await columns[2].inner_text()).strip()
                            self.logger.debug(f"Scraped time_played_str for '{name}': '{time_played_str}'")
                            time_played = self.parse_time(time_played_str)

                            last_played_str = (await columns[6].inner_text()).strip()
                            last_played = datetime.strptime(last_played_str, "%d/%b/%Y").date()

                            # Update or insert the game data
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
                self.logger.info("Recent games data updated and data inserted into the database.")

            # Update initials mapping
            await self.update_initials_mapping()
        except Exception as e:
            self.logger.error(f"Error during recent games data update: {e}", exc_info=True)

    async def update_initials_mapping(self):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT name FROM games") as cursor:
                games = await cursor.fetchall()
        self.initials_mapping = {}
        for game in games:
            name = game[0]
            initials = self.generate_initials(name)
            self.initials_mapping[initials.lower()] = name
            self.logger.debug(f"Updated initials mapping: '{initials.lower()}' for game '{name}'")

    def generate_initials(self, title):
        # Remove any non-alphanumeric characters and replace with space
        title_cleaned = re.sub(r"[^A-Za-z0-9 ]+", "", title)
        # Split the title into words
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
            # Try to parse as a float directly (assuming hours)
            value = float(time_str)
            total_minutes = value * 60
            self.logger.debug(f"Parsed '{time_str}' as {total_minutes} minutes (assumed hours).")
        except ValueError:
            # If that fails, parse as 'number unit' pairs
            parts = time_str.split()
            i = 0
            while i < len(parts):
                try:
                    value = float(parts[i])
                    if i + 1 < len(parts):
                        unit = parts[i + 1].rstrip("s").lower()
                        i += 2
                    else:
                        # If no unit, default to hours
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
                except (ValueError, IndexError) as e:
                    self.logger.error(f"Error parsing time string '{time_str}': {e}", exc_info=True)
                    break
        return int(total_minutes)

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
                "SELECT name, time_played, last_played FROM games ORDER BY last_played DESC"
            ) as cursor:
                rows = await cursor.fetchall()

        # Prepare data for the sheet
        headers = ["Game Image", "Game Name", "Time Played (hours)", "Last Played"]
        data = [headers]

        for row in rows:
            name, minutes, last_played = row
            game_image_url = await self.get_game_image_url(name)  # Fetch the image URL

            # Convert minutes to hours with two decimal places
            hours_played = minutes / 60.0
            time_played = f"{hours_played:.2f}"

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
                await self.update_recent_games()
                await self.update_google_sheet()
            except Exception as e:
                self.logger.error(f"Error during periodic recent games update: {e}", exc_info=True)
            await asyncio.sleep(86400)  # Sleep for 24 hours

    @commands.command(name="dvp")
    async def did_vulpes_play_it(self, ctx: commands.Context, *, game_name: str):
        self.logger.info(f"dvp command called with game: {game_name}")
        await self.db_initialized.wait()  # Wait for the database to be initialized
        try:
            # Normalize the input
            game_name_normalized = game_name.strip().lower()
            input_initials = self.generate_initials(game_name_normalized)
            self.logger.debug(f"Generated initials '{input_initials}' for input '{game_name_normalized}'")

            # Check if the input matches any known abbreviations
            if game_name_normalized in self.abbreviation_mapping:
                game_name_to_search = self.abbreviation_mapping[game_name_normalized]
                self.logger.debug(
                    f"Input '{game_name_normalized}' matched to abbreviation mapping '{game_name_to_search}'"
                )
            elif input_initials in self.initials_mapping:
                game_name_to_search = self.initials_mapping[input_initials]
                self.logger.debug(f"Initials '{input_initials}' matched to '{game_name_to_search}'")
            else:
                # Proceed with fuzzy matching
                async with aiosqlite.connect(self.db_path) as db:
                    async with db.execute("SELECT name FROM games") as cursor:
                        games = await cursor.fetchall()
                game_names = [game[0] for game in games]
                match = process.extractOne(game_name_normalized, game_names)
                if match and match[1] >= 80:
                    game_name_to_search = match[0]
                    self.logger.debug(f"Fuzzy matched '{game_name_normalized}' to '{game_name_to_search}'")
                else:
                    self.logger.warning("No matches found using fuzzy matching.")
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
                hours, minutes = divmod(time_played, 60)
                last_played_formatted = datetime.strptime(str(last_played), "%Y-%m-%d").strftime("%B %d, %Y")
                await ctx.send(
                    f"@{ctx.author.name}, Vulpes played {game_name_to_search} for {int(hours)}h {int(minutes)}m. Last played on {last_played_formatted}."
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
