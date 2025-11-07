import asyncio
import logging
import pandas as pd
from upstox_auth import get_access_token
from upstox_websocket import UpstoxWebSocket
from data_handler import DataHandler
from strategy import TradingStrategy
from order_manager import OrderManager
from historical_loader import preload_candles  # if you use preloading

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class MainApp:
    def __init__(self):
        self.access_token = None
        self.order_manager = None
        self.strategy = None
        self.data_handler = None
        self.websocket = None

    async def run(self):
        logging.info("🚀 Starting the trading application")

        # ✅ Get Access Token
        self.access_token = get_access_token()
        if not self.access_token:
            logging.error("❌ Failed to get access token.")
            return

        # ✅ Load stock list (ISIN-based)
        stocks_df = pd.read_csv("stocks.csv")

        # Convert ISINs into Upstox instrument keys
        instrument_keys = [f"NSE_EQ|{row['ISIN']}" for index, row in stocks_df.iterrows()]
        instrument_to_symbol = {
            f"NSE_EQ|{row['ISIN']}": row['symbol'] for index, row in stocks_df.iterrows()
        }

        logging.info(f"✅ Instruments to subscribe: {instrument_keys}")

        # ✅ Initialize order manager & strategy
        self.order_manager = OrderManager(self.access_token)
        self.strategy = TradingStrategy(self.order_manager)

        # ✅ Preload candles (optional, if using historical_loader)
        try:
            initial_data = preload_candles(self.access_token, instrument_keys)
            logging.info("📊 Preloaded last 400 candles for each instrument.")
        except Exception as e:
            logging.warning(f"⚠️ Could not preload candles: {e}")
            initial_data = None

        # ✅ Initialize data handler
        self.data_handler = DataHandler(
            access_token=self.access_token,
            instrument_keys=instrument_keys,
            instrument_to_symbol=instrument_to_symbol,
            historical_data=initial_data,
            tick_callback=None,
            strategy_callback=self.strategy.on_new_candle
        )

        # ✅ Connect to WebSocket
        self.websocket = UpstoxWebSocket(
            self.access_token,
            self.data_handler,
            instrument_keys
        )

        logging.info("📡 Connecting to the WebSocket...")
        await self.websocket.connect()

        # Keep main thread alive
        while True:
            await asyncio.sleep(1)


if __name__ == "__main__":
    app = MainApp()
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        logging.warning("🛑 Application stopped by user.")
    except Exception as e:
        logging.error("❌ An unexpected error occurred in the main application.", exc_info=True)