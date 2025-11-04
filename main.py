import asyncio
import logging
import pandas as pd
from upstox_auth import get_access_token
from upstox_websocket import UpstoxWebSocket
from data_handler import DataHandler
from strategy import TradingStrategy
from order_manager import OrderManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class MainApp:
    def __init__(self):
        self.access_token = None
        self.order_manager = None
        self.strategy = None
        self.data_handler = None
        self.websocket = None

    async def run(self):
        logging.info("Starting the trading application...")

        self.access_token = get_access_token()
        if not self.access_token:
            logging.error("Failed to get access token. Exiting.")
            return

        self.order_manager = OrderManager(self.access_token)
        self.strategy = TradingStrategy(self.order_manager)

        stocks_df = pd.read_csv('stocks.csv')
        instrument_keys = [f"NSE_EQ|{isin}" for isin in stocks_df['ISIN']]
        instrument_to_symbol = {f"NSE_EQ|{row['ISIN']}": row['symbol'] for index, row in stocks_df.iterrows()}

        self.data_handler = DataHandler(
            instrument_keys=instrument_keys,
            access_token=self.access_token,
            instrument_to_symbol=instrument_to_symbol,
            strategy_callback=self.strategy.run_strategy,
            tick_callback=self.strategy.check_for_sell_signal
        )
        self.websocket = UpstoxWebSocket(self.access_token, self.data_handler, instrument_keys)

        logging.info("Connecting to the WebSocket...")
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
