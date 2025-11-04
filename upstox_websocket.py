import asyncio
import json
import ssl
import websockets
import logging
import requests
from google.protobuf.json_format import MessageToDict
from upstox_client.feeder.proto import MarketDataFeedV3_pb2 as pb

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class UpstoxWebSocket:
    def __init__(self, access_token, data_handler, instrument_keys):
        self.access_token = access_token
        self.data_handler = data_handler
        self.instrument_keys = instrument_keys
        self.ws = None

    def _get_market_data_feed_authorize(self):
        """Get authorization for market data feed."""
        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {self.access_token}'
        }
        url = 'https://api.upstox.com/v3/feed/market-data-feed/authorize'
        api_response = requests.get(url=url, headers=headers)
        return api_response.json()

    def _decode_protobuf(self, buffer):
        """Decode protobuf message."""
        feed_response = pb.FeedResponse()
        feed_response.ParseFromString(buffer)
        return feed_response

    async def connect(self):
        """Fetch market data using WebSocket and print it."""
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        response = self._get_market_data_feed_authorize()

        async with websockets.connect(response["data"]["authorized_redirect_uri"], ssl=ssl_context) as websocket:
            logging.info('Connection established')
            self.ws = websocket

            await asyncio.sleep(1)

            data = {
                "guid": "someguid",
                "method": "sub",
                "data": {
                    "mode": "full",
                    "instrumentKeys": self.instrument_keys
                }
            }

            binary_data = json.dumps(data).encode('utf-8')
            await self.ws.send(binary_data)

            while True:
                message = await self.ws.recv()
                decoded_data = self._decode_protobuf(message)
                data_dict = MessageToDict(decoded_data)
                self.data_handler.process_tick(data_dict)
