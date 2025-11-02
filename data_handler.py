import pandas as pd
import os
import logging
from datetime import datetime
from upstox_client.feeder.proto import MarketDataFeedV3_pb2 as pb

class DataHandler:
    def __init__(self, instrument_keys, strategy_callback=None, tick_callback=None):
        self.instrument_keys = instrument_keys
        self.strategy_callback = strategy_callback
        self.tick_callback = tick_callback
        self.data_dir = "candle_data"
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        self.candle_data = {key: self._load_historical_data(key) for key in instrument_keys}
        self.current_candle = {key: {} for key in instrument_keys}

    def _load_historical_data(self, instrument_key):
        filepath = os.path.join(self.data_dir, f"{instrument_key}.csv")
        if os.path.exists(filepath):
            try:
                df = pd.read_csv(filepath, index_col='timestamp', parse_dates=True)
                logging.info(f"Loaded {len(df)} historical candles for {instrument_key}")
                return df
            except Exception as e:
                logging.error(f"Error loading historical data for {instrument_key}: {e}")
                return pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
        else:
            logging.warning(f"No historical data found for {instrument_key}. Starting fresh.")
            return pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])

    def _save_data(self, instrument_key):
        filepath = os.path.join(self.data_dir, f"{instrument_key}.csv")
        self.candle_data[instrument_key].to_csv(filepath)

    def process_tick(self, market_data_feed):
        if self.tick_callback:
            self.tick_callback(market_data_feed)

        if market_data_feed.type == pb.Type.live_feed or market_data_feed.type == pb.Type.initial_feed:
            for instrument_key, feed in market_data_feed.feeds.items():
                if feed.HasField("ltpc"):
                    self._build_candle_from_tick(instrument_key, feed.ltpc)

    def _build_candle_from_tick(self, instrument_key, ltpc_data):
        try:
            ltp = ltpc_data.ltp
            volume = ltpc_data.ltq

            # Use exchange timestamp if available, otherwise use system time
            timestamp_ms = ltpc_data.ltt
            if timestamp_ms:
                timestamp = pd.to_datetime(timestamp_ms, unit='ms')
            else:
                timestamp = datetime.now()

            if instrument_key not in self.instrument_keys:
                return

            candle_timestamp = timestamp.replace(second=0, microsecond=0, minute=timestamp.minute - timestamp.minute % 5)

            if not self.current_candle[instrument_key] or self.current_candle[instrument_key]['timestamp'] != candle_timestamp:
                if self.current_candle[instrument_key]:
                    self._add_candle(instrument_key, self.current_candle[instrument_key])

                self.current_candle[instrument_key] = {
                    'timestamp': candle_timestamp,
                    'open': ltp,
                    'high': ltp,
                    'low': ltp,
                    'close': ltp,
                    'volume': volume
                }
            else:
                candle = self.current_candle[instrument_key]
                candle['high'] = max(candle['high'], ltp)
                candle['low'] = min(candle['low'], ltp)
                candle['close'] = ltp
                candle['volume'] += volume
        except Exception as e:
            logging.error(f"Error processing tick: {e}")

    def _add_candle(self, instrument_key, candle_data):
        df = self.candle_data[instrument_key]

        new_candle = pd.DataFrame([candle_data])
        new_candle.set_index('timestamp', inplace=True)

        df = pd.concat([df, new_candle])

        if len(df) > 400:
            df = df.iloc[-400:]

        self.candle_data[instrument_key] = df
        self._save_data(instrument_key)
        logging.info(f"New 5-min candle for {instrument_key}: {candle_data}")

        if self.strategy_callback:
            self.strategy_callback(instrument_key, self.get_candle_data(instrument_key))

    def get_candle_data(self, instrument_key):
        return self.candle_data.get(instrument_key)
