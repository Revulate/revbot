import aiohttp
import datetime
import base64
from logger import logger
import json
import os
from dotenv import load_dotenv, set_key

class TwitchAPI:
    """Utility class for interacting with the Twitch Helix API."""

    TOKEN_URL = "https://id.twitch.tv/oauth2/token"
    BASE_URL = "https://api.twitch.tv/helix"
    TOKEN_GENERATOR_BASE_URL = "https://twitchtokengenerator.com/api"

    def __init__(self, client_id, client_secret, access_token=None, refresh_token=None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.oauth_token = access_token
        self.refresh_token = refresh_token
        self.token_expiry = None
        self.session = None

        if not self.client_id or not self.client_secret:
            raise ValueError("CLIENT_ID and CLIENT_SECRET must be provided.")

        self.load_tokens()
        if self.oauth_token and self.refresh_token:
            self.save_tokens()  # Save tokens if they were provided in the constructor

    async def initialize_session(self):
        """Initialize the aiohttp session."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()

    async def close_session(self):
        """Close the aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()

    def load_tokens(self):
        """Load tokens from file and environment variables."""
        self._load_tokens_from_file()
        self._load_tokens_from_env()

    def _load_tokens_from_file(self):
        """Load tokens from a file."""
        token_file = "twitch_tokens.json"
        logger.info(f"Attempting to load tokens from {token_file}")
        try:
            if os.path.exists(token_file):
                with open(token_file, "r") as f:
                    data = json.load(f)
                    self.oauth_token = data.get("access_token")
                    self.refresh_token = data.get("refresh_token")
                    expiry = data.get("expiry")
                    self.token_expiry = datetime.datetime.fromisoformat(expiry) if expiry else None
                logger.info("Tokens loaded successfully from file")
            else:
                logger.info(f"Token file {token_file} not found")
        except json.JSONDecodeError:
            logger.error("Error decoding saved tokens. Will authenticate from scratch.")
        except Exception as e:
            logger.error(f"Unexpected error loading tokens from file: {e}")

    def _load_tokens_from_env(self):
        """Load tokens from environment variables."""
        load_dotenv()
        env_access_token = os.getenv("ACCESS_TOKEN")
        env_refresh_token = os.getenv("REFRESH_TOKEN")
        if env_access_token:
            self.oauth_token = env_access_token
        if env_refresh_token:
            self.refresh_token = env_refresh_token
        logger.info("Tokens loaded from environment variables")

    def save_tokens(self):
        """Save tokens to both file and environment variables."""
        self._save_tokens_to_file()
        self._save_tokens_to_env()

    def _save_tokens_to_file(self):
        """Save tokens to a file."""
        token_file = "twitch_tokens.json"
        logger.info(f"Attempting to save tokens to {token_file}")
        data = {
            "access_token": self.oauth_token,
            "refresh_token": self.refresh_token,
            "expiry": self.token_expiry.isoformat() if self.token_expiry else None,
        }
        try:
            with open(token_file, "w") as f:
                json.dump(data, f)
            logger.info("Tokens saved successfully to file")
        except Exception as e:
            logger.error(f"Error saving tokens to file: {e}")

    def _save_tokens_to_env(self):
        """Save tokens to environment variables."""
        try:
            dotenv_file = os.path.join(os.path.dirname(__file__), '.env')
            set_key(dotenv_file, "ACCESS_TOKEN", self.oauth_token)
            set_key(dotenv_file, "REFRESH_TOKEN", self.refresh_token)
            logger.info("Tokens saved successfully to .env file")
        except Exception as e:
            logger.error(f"Error saving tokens to .env file: {e}")

    async def ensure_token_valid(self):
        """Ensure the OAuth token is valid, refreshing if necessary."""
        if not self.oauth_token or (self.token_expiry and datetime.datetime.now() >= self.token_expiry):
            await self.refresh_oauth_token()

    async def refresh_oauth_token(self):
        """Refresh OAuth token using refresh token if available, otherwise use client credentials flow."""
        if self.refresh_token:
            success = await self._refresh_token_with_refresh_token()
            if not success:
                await self._refresh_token_with_client_credentials()
        else:
            await self._refresh_token_with_client_credentials()
        self.save_tokens()  # Save tokens after refreshing

    async def _refresh_token_with_refresh_token(self):
        """Refresh OAuth token using the refresh token."""
        url = f"{self.TOKEN_GENERATOR_BASE_URL}/refresh/{self.refresh_token}"
        await self.initialize_session()
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    self.oauth_token = data.get("access_token")
                    self.refresh_token = data.get("refresh_token")
                    expires_in = data.get("expires_in", 0)
                    self.token_expiry = datetime.datetime.now() + datetime.timedelta(seconds=expires_in)
                    self.save_tokens()  # Save tokens after successful refresh
                    logger.info("OAuth token refreshed successfully using refresh token.")
                    return True
                else:
                    error_msg = f"Failed to refresh OAuth token using refresh token. Status: {response.status}"
                    logger.error(error_msg)
                    return False
        except Exception as e:
            logger.error(f"Exception during token refresh: {e}")
            return False

    async def _refresh_token_with_client_credentials(self):
        """Refresh OAuth token using client credentials flow."""
        url = f"{self.TOKEN_URL}?client_id={self.client_id}&client_secret={self.client_secret}&grant_type=client_credentials"
        await self.initialize_session()
        try:
            async with self.session.post(url) as response:
                if response.status == 200:
                    data = await response.json()
                    self.oauth_token = data.get("access_token")
                    expires_in = data.get("expires_in", 0)
                    self.token_expiry = datetime.datetime.now() + datetime.timedelta(seconds=expires_in)
                    self.save_tokens()  # Save tokens after successful refresh
                    logger.info("OAuth token refreshed successfully using client credentials.")
                else:
                    error_msg = f"Failed to retrieve OAuth token. Status: {response.status}"
                    logger.error(error_msg)
                    raise ValueError(error_msg)
        except Exception as e:
            logger.error(f"Exception during token refresh: {e}")
            raise

    async def api_request(self, endpoint, params=None, method="GET", data=None):
        """Make an API request to Twitch, handling token refresh if needed."""
        await self.ensure_token_valid()
        url = f"{self.BASE_URL}/{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.oauth_token}",
            "Client-ID": self.client_id,
            "Content-Type": "application/json",
        }
        await self.initialize_session()
        try:
            if method == "GET":
                async with self.session.get(url, params=params, headers=headers) as response:
                    return await self._handle_response(response)
            elif method == "POST":
                async with self.session.post(url, params=params, headers=headers, json=data) as response:
                    return await self._handle_response(response)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
        except aiohttp.ClientError as e:
            logger.error(f"HTTP error during API request: {e}")
            raise

    async def _handle_response(self, response):
        """Handle the API response, refreshing the token if necessary."""
        if response.status == 200:
            return await response.json()
        elif response.status == 401:
            logger.warning("Received 401 error. Attempting to refresh token.")
            await self.refresh_oauth_token()
            # Retry the request with the new token
            return await self.api_request(response.url.path, params=response.url.query)
        else:
            error_msg = f"API request failed. Status: {response.status}"
            logger.error(error_msg)
            raise ValueError(error_msg)

    async def get_streams(self, user_logins):
        """Fetch streams for the specified user logins."""
        params = {"user_login": user_logins}
        return await self.api_request("streams", params=params)

    async def get_users(self, user_logins):
        """Fetch user information for the specified user logins."""
        params = {"login": user_logins}
        return await self.api_request("users", params=params)

    # Add other Twitch API methods as needed...

    async def create_auth_flow(self, application_title, scopes):
        """Create an authorization flow for the user."""
        encoded_title = base64.b64encode(application_title.encode()).decode()
        scopes_string = "+".join(scopes)
        url = f"{self.TOKEN_GENERATOR_BASE_URL}/create/{encoded_title}/{scopes_string}"

        await self.initialize_session()
        async with self.session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("success"):
                    return data.get("id"), data.get("message")
                else:
                    logger.error(f"Failed to create auth flow: {data.get('message')}")
                    return None, None
            else:
                logger.error(f"Failed to create auth flow. Status: {response.status}")
                return None, None

    async def check_auth_status(self, flow_id):
        """Check the status of an authorization flow."""
        url = f"{self.TOKEN_GENERATOR_BASE_URL}/status/{flow_id}"

        await self.initialize_session()
        async with self.session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("success"):
                    self.oauth_token = data.get("token")
                    self.refresh_token = data.get("refresh")
                    expires_in = data.get("expires_in", 0)
                    self.token_expiry = datetime.datetime.now() + datetime.timedelta(seconds=expires_in)
                    self.save_tokens()
                    return True
                else:
                    logger.info(f"Auth status: {data.get('message')}")
                    return False
            else:
                logger.error(f"Failed to check auth status. Status: {response.status}")
                return False
