import os
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional, cast

import requests
from dotenv import find_dotenv, set_key
from loguru import logger

from config import POCKET_ACCESS_TOKEN, POCKET_CONSUMER_KEY

POCKET_REQUEST_URL = "https://getpocket.com/v3/oauth/request"
POCKET_AUTHORIZE_URL = "https://getpocket.com/auth/authorize"
POCKET_ACCESS_URL = "https://getpocket.com/v3/oauth/authorize"


class PocketAuth:
    def __init__(self, redirect_uri="http://localhost:8080"):
        self.consumer_key = POCKET_CONSUMER_KEY
        self.redirect_uri = redirect_uri
        self.request_token: Optional[str] = None
        self.access_token: Optional[str] = POCKET_ACCESS_TOKEN
        self.auth_complete = False

    def _post_request(self, url: str, data: dict) -> dict:
        headers = {"Content-Type": "application/x-www-form-urlencoded; charset=UTF8", "X-Accept": "application/json"}
        response = requests.post(url, headers=headers, data=data)
        if response.status_code != 200:
            logger.error(f"Error from Pocket API ({url}): {response.text}")
            response.raise_for_status()
        return response.json()

    def get_request_token(self):
        logger.info("Requesting Pocket request token...")
        data = {"consumer_key": self.consumer_key, "redirect_uri": self.redirect_uri}
        self.request_token = self._post_request(POCKET_REQUEST_URL, data).get("code")
        logger.info(f"Request token obtained: {self.request_token}")

    def authorize_app(self):
        if not self.request_token:
            raise ValueError("Request token not available. Call `get_request_token` first.")

        auth_url = f"{POCKET_AUTHORIZE_URL}?request_token={self.request_token}&redirect_uri={self.redirect_uri}"
        logger.info(f"Redirecting to Pocket for authorization: {auth_url}")
        webbrowser.open(auth_url)

        server = PocketHTTPServer(("localhost", 8080), PocketAuthHandler, self)
        threading.Thread(target=server.serve_forever, daemon=True).start()

        logger.info("Waiting for user authorization...")
        while not self.auth_complete:
            time.sleep(0.1)
        server.shutdown()
        logger.info("Authorization completed.")

    def get_access_token(self):
        logger.info("Converting request token to access token...")
        data = {"consumer_key": self.consumer_key, "code": self.request_token}
        result = self._post_request(POCKET_ACCESS_URL, data)
        self.access_token = result.get("access_token")
        if isinstance(self.access_token, str):
            self._update_env_file("POCKET_ACCESS_TOKEN", self.access_token)
        else:
            logger.error("Access token is None or invalid, cannot update .env file.")
        logger.info(f"Access token obtained: {self.access_token}")

    def authenticate(self):
        self.get_request_token()
        self.authorize_app()
        self.get_access_token()

    def _update_env_file(self, key: str, value: str):
        dotenv_path = find_dotenv()
        if dotenv_path:
            set_key(dotenv_path, key, value)
            os.environ[key] = value
            logger.info(f"{key} updated in .env and environment.")
        else:
            logger.error(".env file not found. Token not saved.")


class PocketHTTPServer(HTTPServer):
    def __init__(self, server_address, RequestHandlerClass, auth_instance):
        super().__init__(server_address, RequestHandlerClass)
        self.auth_instance = auth_instance


class PocketAuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        server = cast(PocketHTTPServer, self.server)
        server.auth_instance.auth_complete = True
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Authorization complete. You can close this window.")

    def log_message(self, *args, **kwargs):
        pass
