# twitch_helix_client.py

import aiohttp
import datetime
from logger import logger

class TwitchAPI:
    """Utility class for interacting with the Twitch Helix API."""

    TOKEN_URL = "https://id.twitch.tv/oauth2/token"
    BASE_URL = "https://api.twitch.tv/helix"

    def __init__(self, client_id, client_secret, access_token=None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.oauth_token = access_token
        self.token_expiry = None

        if not self.client_id or not self.client_secret:
            raise ValueError("CLIENT_ID and CLIENT_SECRET must be provided.")

    async def get_oauth_token(self):
        """Fetch OAuth token for Twitch API."""
        if not self.oauth_token or (self.token_expiry and datetime.datetime.now() >= self.token_expiry):
            await self.refresh_oauth_token()
        return self.oauth_token

    async def refresh_oauth_token(self):
        """Refresh OAuth token using client credentials flow."""
        url = f"{self.TOKEN_URL}?client_id={self.client_id}&client_secret={self.client_secret}&grant_type=client_credentials"
        async with aiohttp.ClientSession() as session:
            async with session.post(url) as response:
                if response.status == 200:
                    data = await response.json()
                    self.oauth_token = data.get("access_token")
                    expires_in = data.get("expires_in", 0)
                    self.token_expiry = datetime.datetime.now() + datetime.timedelta(seconds=expires_in)
                    logger.info("OAuth token refreshed successfully.")
                else:
                    error_msg = f"Failed to retrieve OAuth token. Status: {response.status}"
                    logger.error(error_msg)
                    raise ValueError(error_msg)

    def update_access_token(self, new_token):
        """Update the access token."""
        self.oauth_token = new_token
        self.token_expiry = datetime.datetime.now() + datetime.timedelta(hours=1)
        logger.info("Access token updated.")

    async def request_with_retry(self, url, headers, retries=3):
        """Helper function to retry a request with token refresh on failure."""
        for attempt in range(retries):
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 401:
                        logger.warning("Token expired, refreshing...")
                        self.oauth_token = None
                        await self.refresh_oauth_token()
                    else:
                        if attempt == retries - 1:
                            error_msg = f"Failed request after {retries} attempts: {response.status}"
                            logger.error(error_msg)
                            raise ValueError(error_msg)
        
        error_msg = f"Failed to complete request after {retries} attempts."
        logger.error(error_msg)
        raise ValueError(error_msg)

    async def get_streams(self, user_logins):
        """Fetch streams for the specified user logins."""
        token = await self.get_oauth_token()
        url = f"{self.BASE_URL}/streams?" + "&".join([f"user_login={login}" for login in user_logins])
        headers = {
            "Authorization": f"Bearer {token}",
            "Client-ID": self.client_id
        }
        data = await self.request_with_retry(url, headers)
        return data.get("data", [])

    async def get_users(self, user_logins):
        """Fetch user information for the specified user logins."""
        token = await self.get_oauth_token()
        url = f"{self.BASE_URL}/users?" + "&".join([f"login={login}" for login in user_logins])
        headers = {
            "Authorization": f"Bearer {token}",
            "Client-ID": self.client_id
        }
        data = await self.request_with_retry(url, headers)
        return data.get("data", [])