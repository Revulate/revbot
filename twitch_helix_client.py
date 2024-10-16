import aiohttp
import asyncio
import datetime
from logger import log_error, log_info, log_warning
import os
import urllib.parse
from dotenv import load_dotenv, set_key
import validators


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
        set_key(".env", "ACCESS_TOKEN", self.oauth_token)
        set_key(".env", "REFRESH_TOKEN", self.refresh_token)
        set_key(".env", "TOKEN_EXPIRY", self.token_expiry.isoformat() if self.token_expiry else "")

    async def get_authorization_url(self, scopes):
        state = os.urandom(16).hex()
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
        await self.ensure_session()
        async with self.session.post(self.TOKEN_URL, data=params) as response:
            if response.status == 200:
                data = await response.json()
                self.oauth_token = data["access_token"]
                self.refresh_token = data["refresh_token"]
                self.token_expiry = datetime.datetime.now() + datetime.timedelta(seconds=data["expires_in"])
                self.save_tokens()
                return True
            else:
                log_error(f"Failed to exchange code for token: {await response.text()}")
                return False

    async def refresh_oauth_token(self):
        if not self.refresh_token:
            log_error("No refresh token available")
            return False

        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
        }
        await self.ensure_session()
        try:
            async with self.session.post(self.TOKEN_URL, data=params) as response:
                if response.status == 200:
                    data = await response.json()
                    self.oauth_token = data["access_token"]
                    self.refresh_token = data.get("refresh_token", self.refresh_token)
                    self.token_expiry = datetime.datetime.now() + datetime.timedelta(seconds=data["expires_in"])
                    self.save_tokens()
                    log_info("OAuth token refreshed successfully")
                    return True
                else:
                    log_error(f"Failed to refresh token: {await response.text()}")
                    return False
        except Exception as e:
            log_error(f"Error during token refresh: {e}", exc_info=True)
            return False

    async def ensure_token_valid(self):
        if not self.oauth_token or (self.token_expiry and datetime.datetime.now() >= self.token_expiry):
            success = await self.refresh_oauth_token()
            if not success:
                raise Exception("Failed to refresh OAuth token")
        return True

    async def api_request(self, endpoint, params=None, method="GET", data=None):
        await self.ensure_session()
        await self.ensure_token_valid()

        url = f"{self.BASE_URL}/{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.oauth_token}",
            "Client-ID": self.client_id,
        }

        try:
            if method == "GET":
                async with self.session.get(url, params=params, headers=headers) as response:
                    response.raise_for_status()
                    return await response.json()
            elif method == "POST":
                async with self.session.post(url, params=params, headers=headers, json=data) as response:
                    response.raise_for_status()
                    return await response.json()
        except aiohttp.ClientResponseError as e:
            if e.status == 401:
                if await self.refresh_oauth_token():
                    headers["Authorization"] = f"Bearer {self.oauth_token}"
                    return await self.api_request(endpoint, params, method, data)
            log_error(f"Request failed: {e}")
            raise

    async def get_streams(self, user_logins):
        params = {"user_login": user_logins}
        return await self.api_request("streams", params=params)

    async def get_users(self, user_logins):
        params = {"login": user_logins}
        return await self.api_request("users", params=params)

    async def get_channel_games(self, channel_name):
        try:
            users = await self.get_users([channel_name])
            if not users or "data" not in users or not users["data"]:
                log_warning(f"Could not find user ID for channel: {channel_name}")
                return None

            user_id = users["data"][0]["id"]
            data = await self.api_request(f"channels?broadcaster_id={user_id}")
            return data["data"][0]["game_name"] if data["data"] else None
        except Exception as e:
            log_error(f"Failed to fetch channel info for {channel_name}: {e}")
            return None

    async def get_game_image_url(self, game_name):
        await self.ensure_session()
        headers = {"Client-ID": self.client_id, "Authorization": f"Bearer {self.oauth_token}"}
        params = {"name": game_name}
        url = f"{self.BASE_URL}/games"

        try:
            async with self.session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data["data"]:
                        box_art_url = data["data"][0]["box_art_url"]
                        formatted_url = box_art_url.replace("{width}", "285").replace("{height}", "380")
                        if validators.url(formatted_url):
                            log_info(f"Generated image URL for '{game_name}': {formatted_url}")
                            return formatted_url
                        else:
                            log_warning(f"Invalid image URL generated for '{game_name}': {formatted_url}")
            log_warning(f"No image found for game: {game_name}")
        except Exception as e:
            log_error(f"Error fetching image URL for {game_name}: {e}", exc_info=True)
        return ""

    async def close(self):
        await self.close_session()
