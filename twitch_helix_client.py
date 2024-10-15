import aiohttp
import asyncio
import datetime
import base64
from logger import logger
import json
import os
import random
import urllib.parse
from dotenv import load_dotenv, set_key


class TwitchAPI:
    TOKEN_URL = "https://id.twitch.tv/oauth2/token"
    BASE_URL = "https://api.twitch.tv/helix"
    AUTHORIZE_URL = "https://id.twitch.tv/oauth2/authorize"
    DEVICE_CODE_URL = "https://id.twitch.tv/oauth2/device"

    def __init__(self, client_id, client_secret, redirect_uri):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.oauth_token = None
        self.refresh_token = None
        self.token_expiry = None
        self.session = None
        self.load_tokens()

    def set_session(self, session):
        """Set an external session for API requests."""
        self.session = session

    async def ensure_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()

    async def close_session(self):
        if self.session and not self.session.closed:
            await self.session.close()

    def load_tokens(self):
        load_dotenv()
        self.oauth_token = os.getenv("ACCESS_TOKEN")
        self.refresh_token = os.getenv("REFRESH_TOKEN")
        expiry = os.getenv("TOKEN_EXPIRY")
        self.token_expiry = datetime.datetime.fromisoformat(expiry) if expiry else None

    def save_tokens(self):
        dotenv_file = ".env"
        set_key(dotenv_file, "ACCESS_TOKEN", self.oauth_token)
        set_key(dotenv_file, "REFRESH_TOKEN", self.refresh_token)
        set_key(dotenv_file, "TOKEN_EXPIRY", self.token_expiry.isoformat() if self.token_expiry else "")

    async def get_authorization_url(self, scopes):
        state = base64.urlsafe_b64encode(os.urandom(30)).decode("utf-8")
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "state": state,
        }
        return f"{self.AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    async def exchange_code_for_token(self, code):
        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(self.TOKEN_URL, data=params) as response:
                if response.status == 200:
                    data = await response.json()
                    self.oauth_token = data["access_token"]
                    self.refresh_token = data["refresh_token"]
                    self.token_expiry = datetime.datetime.now() + datetime.timedelta(seconds=data["expires_in"])
                    self.save_tokens()
                    return True
                else:
                    logger.error(f"Failed to exchange code for token: {await response.text()}")
                    return False

    async def refresh_oauth_token(self):
        if not self.refresh_token:
            logger.error("No refresh token available")
            return False

        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.TOKEN_URL, data=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.oauth_token = data["access_token"]
                        self.refresh_token = data.get("refresh_token", self.refresh_token)
                        self.token_expiry = datetime.datetime.now() + datetime.timedelta(seconds=data["expires_in"])
                        self.save_tokens()
                        logger.info("OAuth token refreshed successfully")
                        return True
                    else:
                        logger.error(f"Failed to refresh token: {await response.text()}")
                        return False
        except Exception as e:
            logger.error(f"Error during token refresh: {e}", exc_info=True)
            return False

    async def ensure_token_valid(self):
        if not self.oauth_token or (self.token_expiry and datetime.datetime.now() >= self.token_expiry):
            success = await self.refresh_oauth_token()
            if not success:
                raise Exception("Failed to refresh OAuth token")
        return True

    async def api_request(self, endpoint, params=None, method="GET", data=None):
        await self.ensure_session()

        url = f"{self.BASE_URL}/{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.oauth_token}",
            "Client-ID": self.client_id,
        }

        async def perform_request(session):
            try:
                if method == "GET":
                    async with session.get(url, params=params, headers=headers) as response:
                        response.raise_for_status()
                        return await response.json()
                elif method == "POST":
                    async with session.post(url, params=params, headers=headers, json=data) as response:
                        response.raise_for_status()
                        return await response.json()
            except aiohttp.ClientResponseError as e:
                if e.status == 401:
                    if await self.refresh_oauth_token():
                        headers["Authorization"] = f"Bearer {self.oauth_token}"
                        return await perform_request(session)
                raise

        if self.session:
            return await perform_request(self.session)
        else:
            async with aiohttp.ClientSession() as session:
                return await perform_request(session)

    async def get_streams(self, user_logins):
        params = {"user_login": user_logins}
        return await self.api_request("streams", params=params)

    async def get_users(self, user_logins):
        params = {"login": user_logins}
        return await self.api_request("users", params=params)

    async def start_device_auth_flow(self, scopes):
        params = {"client_id": self.client_id, "scopes": " ".join(scopes)}
        async with aiohttp.ClientSession() as session:
            async with session.post(self.DEVICE_CODE_URL, data=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"Failed to start device auth flow: {await response.text()}")
                    return None

    async def poll_for_device_code_token(self, device_code, interval, expires_in):
        params = {
            "client_id": self.client_id,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        }
        end_time = datetime.datetime.now() + datetime.timedelta(seconds=expires_in)
        while datetime.datetime.now() < end_time:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.TOKEN_URL, data=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.oauth_token = data["access_token"]
                        self.refresh_token = data["refresh_token"]
                        self.token_expiry = datetime.datetime.now() + datetime.timedelta(seconds=data["expires_in"])
                        self.save_tokens()
                        return True
                    elif response.status == 400:
                        error = await response.json()
                        if error.get("message") == "authorization_pending":
                            await asyncio.sleep(interval)
                        else:
                            logger.error(f"Device code error: {error}")
                            return False
                    else:
                        logger.error(f"Unexpected response: {await response.text()}")
                        return False
        logger.error("Device code flow timed out")
        return False

    async def fetch_recent_videos(self, user_id, first=100):
        params = {"user_id": user_id, "first": first, "type": "archive"}
        try:
            data = await self.api_request("videos", params=params)
            logger.info(f"Fetched {len(data['data'])} videos from Twitch API")
            return data["data"]
        except Exception as e:
            logger.error(f"Error fetching recent videos: {e}")
            return []

    async def get_user_id(self, username):
        try:
            users = await self.get_users([username])
            return users["data"][0]["id"] if users["data"] else None
        except Exception as e:
            logger.error(f"Error getting user ID for {username}: {e}")
            return None

    async def get_channel_games(self, channel_name):
        try:
            # First, get the user ID for the given channel name
            users = await self.get_users([channel_name])
            if not users or "data" not in users or not users["data"]:
                logger.error(f"Could not find user ID for channel: {channel_name}")
                return None

            user_id = users["data"][0]["id"]

            # Now use the user ID to fetch channel info
            data = await self.api_request(f"channels?broadcaster_id={user_id}")
            return data["data"][0]["game_name"] if data["data"] else None
        except Exception as e:
            logger.error(f"Failed to fetch channel info for {channel_name}: {e}")
            return None

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

    async def close(self):
        await self.close_session()
