import os
import webbrowser

import requests
from loguru import logger

from config import POCKET_CONSUMER_KEY

POCKET_REQUEST_URL = "https://getpocket.com/v3/oauth/request"
POCKET_AUTHORIZE_URL = "https://getpocket.com/auth/authorize"
POCKET_ACCESS_URL = "https://getpocket.com/v3/oauth/authorize"


class PocketAuth:
    def __init__(self, redirect_uri="http://localhost"):
        self.consumer_key = POCKET_CONSUMER_KEY
        self.redirect_uri = redirect_uri
        self.request_token = os.getenv("POCKET_REQUEST_TOKEN")
        self.access_token = os.getenv("POCKET_ACCESS_TOKEN")

    def get_request_token(self):
        """Step 2: Obtain a request token."""
        logger.info("Requesting Pocket request token...")
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF8",
            "X-Accept": "application/json",
        }
        data = {
            "consumer_key": self.consumer_key,
            "redirect_uri": self.redirect_uri,
        }
        response = requests.post(POCKET_REQUEST_URL, headers=headers, data=data)

        if response.status_code == 200:
            self.request_token = response.json().get("code")
            logger.info(f"Request token obtained: {self.request_token}")
            return self.request_token
        else:
            logger.error(f"Failed to get request token: {response.text}")
            raise Exception("Error obtaining request token.")

    def authorize_app(self):
        """Step 3: Redirect user to Pocket to authorize the request token."""
        if not self.request_token:
            raise ValueError("Request token not available. Call `get_request_token` first.")

        # Construct the authorization URL
        auth_url = f"{POCKET_AUTHORIZE_URL}?request_token={self.request_token}&redirect_uri={self.redirect_uri}"
        logger.info(f"Opening browser to authorize the app: {auth_url}")

        # Open the browser for user to authorize the app
        webbrowser.open(auth_url)

        # Wait for user to authorize
        input("Press Enter after authorizing the app in your browser...")

    def get_access_token(self):
        """Step 5: Convert the request token to an access token."""
        logger.info("Converting request token to access token...")
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF8",
            "X-Accept": "application/json",
        }
        data = {
            "consumer_key": self.consumer_key,
            "code": self.request_token,
        }
        response = requests.post(POCKET_ACCESS_URL, headers=headers, data=data)

        if response.status_code == 200:
            result = response.json()
            self.access_token = result.get("access_token")
            username = result.get("username")
            logger.info(f"Access token obtained: {self.access_token}")
            logger.info(f"Authenticated as: {username}")
            return self.access_token
        else:
            # Log the full error response for debugging
            logger.error(f"Failed to obtain access token. Response: {response.text}")
            logger.error(f"Status Code: {response.status_code}")
            raise Exception(f"Error converting request token to access token: {response.text}")

    def authenticate(self):
        """Complete authentication process and return access token."""
        self.get_request_token()
        self.authorize_app()
        return self.get_access_token()

    def check_authentication_status(self):
        """
        Check if Pocket API credentials (consumer key and access token) are valid.
        Returns a dictionary with the status and details.
        """
        if not self.consumer_key:
            logger.error("Missing Pocket consumer key.")
            return {"status": "error", "message": "Consumer key is missing."}

        if not self.access_token:
            logger.warning("Missing Pocket access token.")
            return {"status": "error", "message": "Access token is missing."}

        # Make a test request to verify the access token
        test_url = "https://getpocket.com/v3/get"
        headers = {"Content-Type": "application/json", "X-Accept": "application/json"}
        payload = {
            "consumer_key": self.consumer_key,
            "access_token": self.access_token,
            "count": 1,  # Minimal request to verify credentials
        }

        try:
            response = requests.post(test_url, headers=headers, json=payload)
            if response.status_code == 200:
                logger.info("Pocket authentication verified successfully.")
                return {"status": "success", "message": "Authentication is valid."}
            elif response.status_code == 401:
                logger.error("Invalid or expired Pocket access token.")
                return {"status": "error", "message": "Invalid or expired access token."}
            else:
                logger.error(f"Unexpected API response: {response.text}")
                return {"status": "error", "message": f"API error: {response.text}"}
        except Exception as e:
            logger.error(f"Error while verifying authentication: {e}")
            return {"status": "error", "message": f"Unexpected error: {str(e)}"}
