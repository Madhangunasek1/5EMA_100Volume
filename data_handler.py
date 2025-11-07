import pandas as pd
import os
import logging
from datetime import datetime, timedelta
import upstox_client
import pytz
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s') 
class DataHandler:
    def __init__(
        self,
        access_token,
        instrument_keys,
        historical_data=None,
        tick_callback=None,
        strategy_callback=None,
        instrument_to_symbol=None,
    ):
        """
        Initialize DataHandler with optional preloaded historical data.
        """
        self.access_token = access_token
        self.instrument_keys = instrument_keys
        self.tick_callback = tick_callback
        self.strategy_callback = strategy_callback
        self.instrument_to_symbol = instrument_to_symbol or {}
        self.data_dir = "candle_data"

        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

        # ✅ Preload data (historical + intraday)
        if historical_data:
            self.candle_data = historical_data
            logging.info("✅ Using preloaded candle data (historical + intraday).")
        else:
            self.candle_data = {
                key: self._load_historical_data(key) for key in instrument_keys
            }

        self.current_candle = {key: {} for key in instrument_keys}
        logging.info("✅ DataHandler initialized with real-time 5-min candle builder.")

    # ---------------------- FILE UTILITIES ----------------------
    def _get_safe_filename(self, instrument_key):
        return self.instrument_to_symbol.get(instrument_key, instrument_key.replace("|", "-"))

    def _save_data(self, instrument_key):
        filepath = os.path.join(self.data_dir, f"{self._get_safe_filename(instrument_key)}.csv")
        self.candle_data[instrument_key].to_csv(filepath)

    # ---------------------- HISTORICAL + INTRADAY DATA (V3) ----------------------
    def _fetch_combined_candles(self, instrument_key):
        """Fetch last 400 candles by combining V3 Historical + Intraday."""
        try:
            configuration = upstox_client.Configuration()
            configuration.access_token = self.access_token
            api = upstox_client.HistoryV3Api(upstox_client.ApiClient(configuration))

            today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
            yday = today - timedelta(days=1)
            from_date = (today - timedelta(days=15)).isoformat()  # 15 days lookback

            # 1️⃣ Historical candles till yesterday
            df_hist = self._safe_candles_df(
                api.get_historical_candle_data1(
                    instrument_key,
                    "minutes",
                    "5",
                    to_date=yday.isoformat(),
                    from_date=from_date,
                )
            )

            # 2️⃣ Intraday candles for today
            df_intraday = self._safe_candles_df(
                api.get_intra_day_candle_data(
                    instrument_key,
                    unit="minutes",
                    interval="5",
                )
            )

            # 3️⃣ Combine both and clean
            df = pd.concat([df_hist, df_intraday])
            df = df[~df.index.duplicated(keep="last")].sort_index()
            df = df.iloc[-400:]  # Keep last 400

            filepath = os.path.join(self.data_dir, f"{self._get_safe_filename(instrument_key)}.csv")
            df.to_csv(filepath)
            logging.info(f"📊 Combined historical+intraday saved for {instrument_key}")
            return df

        except Exception as e:
            logging.error(f"❌ Error fetching data for {instrument_key}: {e}", exc_info=True)
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    def _safe_candles_df(self, resp):
        """Extracts candles safely and converts to DataFrame."""
        try:
            candles = getattr(getattr(resp, "data", None), "candles", None)
            if candles is None and isinstance(resp, dict):
                candles = resp.get("data", {}).get("candles", [])
        except Exception:
            candles = []

        if not candles:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        cols = ["timestamp", "open", "high", "low", "close", "volume", "open_interest"]
        df = pd.DataFrame(candles, columns=cols[: len(candles[0])])
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=False)
        df.set_index("timestamp", inplace=True)
        df = df.sort_index()
        df = df.apply(pd.to_numeric, errors="coerce")
        return df

    def _load_historical_data(self, instrument_key):
        """Load from CSV if available; otherwise fetch combined candles."""
        filepath = os.path.join(self.data_dir, f"{self._get_safe_filename(instrument_key)}.csv")
        if os.path.exists(filepath):
            try:
                df = pd.read_csv(filepath, index_col="timestamp", parse_dates=True)
                logging.info(f"✅ Loaded {len(df)} historical candles for {instrument_key}")
                return df
            except Exception as e:
                logging.error(f"⚠️ Error loading historical data for {instrument_key}: {e}")

        logging.warning(f"Fetching fresh combined candles for {instrument_key}. Fetching fresh...")
        return self._fetch_combined_candles(instrument_key)
 
    # ---------------------- LIVE TICK HANDLING ----------------------
    def process_tick(self, market_data_feed):
        """
        Process incoming tick data from Upstox websocket.
        Updates current candle, closes old candle if needed,
        triggers strategy and tick callback.
        """
        try:
            feed_type = market_data_feed.get('type')
            if feed_type not in ['live_feed', 'initial_feed']:
                return
            logging.info(f"Tick received in DataHanler:{list(market_data_feed.get('feeds',{}).keys())[:5]}")

            # --- Extract correct sub-feed based on structure ---
            feeds = market_data_feed.get("feeds", {})
            for instrument_key, feed in feeds.items():
                try:
                    # 🧭 Step 1: Collect all possible nested sections
                    possible_sections = [
                        feed,
                        feed.get("fullFeed"),
                        feed.get("marketFF"),
                        feed.get("marketLevel"),
                        feed.get("quote"),
                        feed.get("marketOHLC"),
                    ]
            
                    # 🧭 Step 2: Also explore one level deeper (e.g., marketFF → ltpc)
                    deep_sections = []
                    for s in possible_sections:
                        if isinstance(s, dict):
                            deep_sections.extend(list(s.values()))
            
                    all_sections = possible_sections + deep_sections
            
                    # 🧭 Step 3: Find dictionary with 'ltp' key
                    ltpc_data = next(
                        (s for s in all_sections if isinstance(s, dict) and ("ltp" in s or "ltpc" in s or "ltq" in s)),
                        None
                    )
            
                    if not ltpc_data:
                        logging.debug(f"⚠️ No LTP section found for {instrument_key}. Keys: {list(feed.keys())}")
                        continue
            
                    # 🧩 Step 4: Handle 'ltpc' wrapper
                    if "ltpc" in ltpc_data:
                        ltpc_data = ltpc_data["ltpc"]
            
                    # ✅ Step 5: Extract core tick data
                    ltp = float(ltpc_data.get("ltp") or ltpc_data.get("last_price") or 0)
                    volume = int(ltpc_data.get("ltq", 0))
                    timestamp_ms = ltpc_data.get("ltt")
                    timestamp = pd.to_datetime(timestamp_ms, unit="ms", utc=True).tz_convert("Asia/Kolkata") if timestamp_ms else datetime.now().astimezone().astimezone(pytz.timezone("Asia/Kolkata"))
            
                    logging.info(
                        f"✅ Parsed tick for {instrument_key} | LTP={ltp} | VOL={volume} | TIME={timestamp.strftime('%H:%M:%S')}"
                    )
            
                    # ⚙️ Step 6: Build/update candle
                    if ltp > 0:
                        logging.info(f"⚙️ Calling _build_candle_from_tick for {instrument_key}")
                        self._build_candle_from_tick(
                            instrument_key,
                            {"ltp": ltp, "ltq": volume, "ltt": timestamp_ms},
                        )
            
                except Exception as e:
                    logging.error(f"❌ Error parsing tick for {instrument_key}: {e}", exc_info=True)    

        except Exception as e:
            logging.error(f"❌ Error in process_tick: {e}", exc_info=True)
 
    # ---------------------- CANDLE BUILDING ----------------------
    def _build_candle_from_tick(self, instrument_key, ltpc_data):
        try:
            ltp = ltpc_data.get('ltp')
            volume = ltpc_data.get('ltq', 0)
            timestamp_ms = ltpc_data.get('ltt')
            timestamp = pd.to_datetime(timestamp_ms, unit="ms", utc=True).tz_convert("Asia/Kolkata") if timestamp_ms else datetime.now().astimezone().astimezone(pytz.timezone("Asia/Kolkata"))
            logging.info(f"Adding tick to candle: {instrument_key} | LTP = {ltp} | Vol = {volume} | Time = {timestamp.strftime('%H:%M:%S')}")
            if instrument_key not in self.instrument_keys:
                return
 
            # Align to nearest 5-min boundary
            candle_timestamp = timestamp.replace(
                second=0, microsecond=0, minute=timestamp.minute - timestamp.minute % 5
            )
 
            current = self.current_candle[instrument_key]
 
            # If new 5-min slot, close the previous candle
            if not current or current.get('timestamp') != candle_timestamp:
                if current:
                    self._add_candle(instrument_key, current)
                self.current_candle[instrument_key] = {
                    'timestamp': candle_timestamp,
                    'open': ltp,
                    'high': ltp,
                    'low': ltp,
                    'close': ltp,
                    'volume': volume
                }
            else:
                # Update ongoing candle
                candle = self.current_candle[instrument_key]
                candle['high'] = max(candle['high'], ltp)
                candle['low'] = min(candle['low'], ltp)
                candle['close'] = ltp
                candle['volume'] += volume
 
        except Exception as e:
            logging.error(f"❌ Error building candle: {e}", exc_info=True)
 
    def _add_candle(self, instrument_key, candle_data):
        try:
            df = self.candle_data[instrument_key]
            new_candle = pd.DataFrame([candle_data])
            new_candle.set_index('timestamp', inplace=True)
            df = pd.concat([df, new_candle])
            df = df.iloc[-400:]
            self.candle_data[instrument_key] = df
            self._save_data(instrument_key)
 
            logging.info(f"🕐 New 5-min candle for {instrument_key}: {candle_data}")
            
            print(f"Candle closed at{candle_data['timestamp']} for {instrument_key} | Close:{candle_data['close']} | Vol:{candle_data['volume']}")

            # Trigger strategy callback on new candle
            if self.strategy_callback:
                self.strategy_callback(instrument_key, self.get_candle_data(instrument_key))
 
        except Exception as e:
            logging.error(f"❌ Error adding new candle for {instrument_key}: {e}", exc_info=True)
 
    def get_candle_data(self, instrument_key):
        return self.candle_data.get(instrument_key)

