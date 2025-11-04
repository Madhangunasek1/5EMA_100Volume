import upstox_client
import asyncio
import pandas as pd
import logging
from config import API_KEY, API_SECRET, REDIRECT_URI
from upstox_auth import get_access_token

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class UpstoxWebSocket:
    def __init__(self, access_token, data_handler, instrument_keys):
        self.access_token = access_token
        self.data_handler = data_handler
        self.instrument_keys = instrument_keys
        self.ws = None

    def _get_api_configuration(self):
        """
        Returns the API configuration object.
        """
        configuration = upstox_client.Configuration()
        configuration.access_token = self.access_token
        return configuration

    def on_open(self):
        logging.info("WebSocket connection opened.")
        self.subscribe()

    def on_message(self, message):
        # Pass the dictionary to the data handler
        self.data_handler.process_tick(message)

    def on_error(self, error):
        logging.error(f"WebSocket error: {error}")

    def on_close(self):
        logging.info("WebSocket connection closed.")

    def subscribe(self):
        if self.ws and self.instrument_keys:
            self.ws.subscribe(self.instrument_keys, "full")

    async def connect(self):
        """
        Connects to the Upstox WebSocket API and starts streaming data.
        """
        configuration = self._get_api_configuration()
        api_client = upstox_client.ApiClient(configuration)

        self.ws = upstox_client.MarketDataStreamerV3(api_client)
        self.ws.on("open", self.on_open)
        self.ws.on("message", self.on_message)
        self.ws.on("error", self.on_error)
        self.ws.on("close", self.on_close)

        # This will run in a separate thread
        self.ws.connect()
