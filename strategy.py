import pandas as pd
import logging
from datetime import date

class TradingStrategy:
    def __init__(self, order_manager):
        self.order_manager = order_manager
        self.signals = []
        self.daily_trade_count = 0
        self.max_daily_trades = 2
        self.traded_stocks_today = {}
        self.condition1_met_stocks = {}

    def new_day(self):
        """
        Resets the daily limits and tracking.
        """
        self.daily_trade_count = 0
        self.traded_stocks_today = {}
        self.condition1_met_stocks = {}
        logging.info("New trading day started. Daily limits reset.")

    def run_strategy(self, instrument_key, candle_data):
        """
        Runs the trading strategy when a new candle is formed.
        """
        if date.today() not in self.traded_stocks_today:
            self.new_day()

        if len(candle_data) < 100:
            logging.warning(f"Not enough data for {instrument_key}. Need 100 candles, have {len(candle_data)}.")
            return

        candle_data['5sma'] = candle_data['close'].rolling(window=5).mean()
        candle_data['100vma'] = candle_data['volume'].rolling(window=100).mean()

        latest_candle = candle_data.iloc[-1]

        # ✅ Add this line below
        logging.info(f"🎯 Strategy evaluated for {instrument_key} | Last Close={latest_candle['close']}")
        
        condition1_met = (
            latest_candle['low'] > latest_candle['5sma'] and
            latest_candle['volume'] > 5 * latest_candle['100vma']
        )

        if condition1_met:
            self.condition1_met_stocks[instrument_key] = latest_candle['low']
            logging.info(f"Condition 1 met for {instrument_key}. Monitoring for low break at {latest_candle['low']}.")

    def check_for_sell_signal(self, tick_data):
        """
        Checks for a sell signal on every incoming tick.
        """
        instrument_key = tick_data.get('instrument_key')
        ltp = tick_data.get('last_price')

        if instrument_key in self.condition1_met_stocks:
            condition1_low = self.condition1_met_stocks[instrument_key]
            if ltp < condition1_low:
                logging.info(f"Condition 2 met for {instrument_key}. Placing sell order.")
                if self._can_place_trade(instrument_key):
                    self.place_sell_order(instrument_key, ltp)
                    del self.condition1_met_stocks[instrument_key]

    def _can_place_trade(self, instrument_key):
        if self.daily_trade_count >= self.max_daily_trades:
            logging.warning("Max daily trades reached. No more orders will be placed today.")
            return False
        if self.traded_stocks_today.get(instrument_key, 0) > 0:
            logging.warning(f"Already traded {instrument_key} today. Skipping new order.")
            return False
        return True

    def place_sell_order(self, instrument_key, price):
        stop_loss = price * 1.012
        profit_target = price * 0.97

        order_id = self.order_manager.place_bracket_order(
            instrument_key=instrument_key,
            price=price,
            stop_loss=stop_loss,
            profit_target=profit_target
        )

        if order_id:
            signal = {
                'Date': date.today(),
                'Sell Entry Time': pd.to_datetime('now').time(),
                'Sell Price': price,
                'Stop Loss': stop_loss,
                'Profit Target': profit_target,
                'Order ID': order_id
            }
            self.signals.append(signal)
            self.save_signals()
            self.daily_trade_count += 1
            self.traded_stocks_today[instrument_key] = 1

    def save_signals(self):
        if self.signals:
            df = pd.DataFrame(self.signals)
            df.to_csv("strategy_results.csv", index=False)
            logging.info("Strategy results saved to strategy_results.csv")
    
    def on_new_candle(self, instrument_key, candle_data):
        """
        This method is called every time a new 5-minute candle is completed.
        """
        try:
            logging.info(f"🕐 New candle received for {instrument_key} | total candles: {len(candle_data)}")
            self.run_strategy(instrument_key, candle_data)
        except Exception as e:
            logging.error(f"❌ Error in on_new_candle for {instrument_key}: {e}", exc_info=True)
