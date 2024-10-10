import os
import aiohttp
import datetime
from dotenv import load_dotenv

load_dotenv()

class TwitchAPI:
    """
    Utility class for interacting with the Twitch Helix API.
    Handles fetching stream and user information.
    """

    TOKEN_URL = "https://id.twitch.tv/oauth2/token"
    BASE_URL = "https://api.twitch.tv/helix"

    def __init__(self):
        self.client_id = os.getenv("CLIENT_ID")
        self.client_secret = os.getenv("CLIENT_SECRET")
        self.oauth_token = None
        self.token_expiry = None

        if not self.client_id or not self.client_secret:
            raise ValueError("CLIENT_ID and CLIENT_SECRET must be set in the environment variables.")

    async def get_oauth_token(self):
        """Fetch OAuth token for Twitch API."""
        # Refresh token if expired
        if not self.oauth_token or (self.token_expiry and datetime.datetime.now() >= self.token_expiry):
            url = f"{self.TOKEN_URL}?client_id={self.client_id}&client_secret={self.client_secret}&grant_type=client_credentials"
            async with aiohttp.ClientSession() as session:
                async with session.post(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.oauth_token = data.get("access_token")
                        expires_in = data.get("expires_in", 0)
                        self.token_expiry = datetime.datetime.now() + datetime.timedelta(seconds=expires_in)
                    else:
                        raise ValueError("Failed to retrieve OAuth token. Please check your credentials.")
        return self.oauth_token

    async def get_streams(self, user_logins):
        """Fetch streams for the specified user logins."""
        token = await self.get_oauth_token()
        url = f"{self.BASE_URL}/streams?" + "&".join([f"user_login={login}" for login in user_logins])
        headers = {
            "Authorization": f"Bearer {token}",
            "Client-ID": self.client_id
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("data", [])
                elif response.status == 401:
                    self.oauth_token = None  # Reset the token to force refresh
                    raise ValueError("Unauthorized request. Token might be expired.")
                else:
                    raise ValueError(f"Failed to fetch streams: {response.status}")

    async def get_users(self, user_logins):
        """Fetch user information for the specified user logins."""
        token = await self.get_oauth_token()
        url = f"{self.BASE_URL}/users?" + "&".join([f"login={login}" for login in user_logins])
        headers = {
            "Authorization": f"Bearer {token}",
            "Client-ID": self.client_id
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("data", [])
                elif response.status == 401:
                    self.oauth_token = None  # Reset the token to force refresh
                    raise ValueError("Unauthorized request. Token might be expired.")
                else:
                    raise ValueError(f"Failed to fetch users: {response.status}")

# Example usage
# twitch_api = TwitchAPI()
# streams = await twitch_api.get_streams(["afro", "cohhcarnage"])
# users = await twitch_api.get_users(["afro", "cohhcarnage"])