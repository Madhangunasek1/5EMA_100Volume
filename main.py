import asyncio
import logging
import pandas as pd
from upstox_auth import get_access_token
from upstox_websocket import UpstoxWebSocket
from data_handler import DataHandler
from strategy import TradingStrategy
from order_manager import OrderManager
from historical_loader import preload_candles

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class MainApp:
    def __init__(self):
        self.access_token = None
        self.order_manager = None
        self.strategy = None
        self.data_handler = None
        self.websocket = None

    async def run(self):
        logging.info("Starting the trading application.")

        # Step 1: get access token
        self.access_token = get_access_token()
        if not self.access_token:
            logging.error("Failed to get access token. Exiting.")
            return

        # Step 2: load your stock symbols
        stocks_df = pd.read_csv("stocks.csv")
        instruments_list = stocks_df['instrument_key'].tolist()
        logging.info(f"📦 Loaded {len(instruments_list)} instruments from CSV.")

        # Step 3: preload last 400 candles for all instruments
        from historical_loader import preload_candles
        initial_data = preload_candles(self.access_token, instruments_list)

        # Step 4: Initialize OrderManager, Strategy, DataHandler
        self.order_manager = OrderManager(self.access_token)
        self.strategy = TradingStrategy(self.order_manager)

        from data_handler import DataHandler
        self.data_handler = DataHandler(
            access_token=self.access_token,
            instrument_keys=instruments_list,
            historical_data=initial_data,  # ✅ preloaded history
            tick_callback=None,
            strategy_callback=self.strategy.on_new_candle
        )

        # Step 5: initialize and connect websocket
        from upstox_websocket import UpstoxWebSocket
        self.websocket = UpstoxWebSocket(
            access_token=self.access_token,
            instrument_keys=instruments_list,
            data_handler=self.data_handler
        )

        logging.info("🚀 All systems ready. Starting live data stream...")
        await self.websocket.connect()

        # Keep the main thread alive
        while True:
            await asyncio.sleep(1)

if __name__ == "__main__":
    app = MainApp()
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        logging.info("Application stopped by user.")
    except Exception as e:
        logging.error(f"An unexpected error occurred in the main application: {e}", exc_info=True)
