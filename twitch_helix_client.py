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

    async def initialize_session(self):
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
        async with aiohttp.ClientSession() as session:
            async with session.post(self.TOKEN_URL, data=params) as response:
                if response.status == 200:
                    data = await response.json()
                    self.oauth_token = data["access_token"]
                    self.refresh_token = data.get("refresh_token", self.refresh_token)
                    self.token_expiry = datetime.datetime.now() + datetime.timedelta(seconds=data["expires_in"])
                    self.save_tokens()
                    return True
                else:
                    logger.error(f"Failed to refresh token: {await response.text()}")
                    return False

    async def ensure_token_valid(self):
        if not self.oauth_token or (self.token_expiry and datetime.datetime.now() >= self.token_expiry):
            return await self.refresh_oauth_token()
        return True

    async def api_request(self, endpoint, params=None, method="GET", data=None):
        if not await self.ensure_token_valid():
            raise Exception("Failed to obtain a valid token")

        url = f"{self.BASE_URL}/{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.oauth_token}",
            "Client-ID": self.client_id,
        }

        async with aiohttp.ClientSession() as session:
            for _ in range(2):  # Try twice: once with current token, once after refreshing
                try:
                    if method == "GET":
                        async with session.get(url, params=params, headers=headers) as response:
                            if response.status == 401:
                                if await self.refresh_oauth_token():
                                    headers["Authorization"] = f"Bearer {self.oauth_token}"
                                    continue
                                else:
                                    raise Exception("Failed to refresh token")
                            response.raise_for_status()
                            return await response.json()
                    elif method == "POST":
                        async with session.post(url, params=params, headers=headers, json=data) as response:
                            if response.status == 401:
                                if await self.refresh_oauth_token():
                                    headers["Authorization"] = f"Bearer {self.oauth_token}"
                                    continue
                                else:
                                    raise Exception("Failed to refresh token")
                            response.raise_for_status()
                            return await response.json()
                except aiohttp.ClientResponseError as e:
                    if e.status != 401:
                        raise
                break  # If we get here, we've either succeeded or failed after a refresh
            raise Exception("Failed to complete API request")

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
