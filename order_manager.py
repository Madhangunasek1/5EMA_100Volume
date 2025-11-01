import upstox_client
import logging

class OrderManager:
    def __init__(self, access_token):
        self.api_client = self._get_api_client(access_token)

    def _get_api_client(self, access_token):
        """
        Initializes the Upstox API client with the access token.
        """
        configuration = upstox_client.Configuration()
        configuration.access_token = access_token
        return upstox_client.ApiClient(configuration)

    def place_bracket_order(self, instrument_key, price, stop_loss, profit_target):
        """
        Places a bracket order with a stop loss and profit target.
        """
        try:
            api_instance = upstox_client.OrderApi(self.api_client)
            order_request = upstox_client.PlaceOrderRequest(
                quantity=1,  # Example quantity
                product="D",  # Intraday
                validity="DAY",
                price=price,
                tag="signal_trade",
                order_type="LIMIT", # Bracket orders are typically limit orders
                instrument_token=instrument_key,
                transaction_type="SELL",
                trigger_price=0, # Not a trigger order
                stop_loss=round(stop_loss - price, 2), # Price difference
                square_off=round(price - profit_target, 2) # Price difference
            )
            api_response = api_instance.place_order(api_version="v2", body=order_request)
            logging.info(f"Bracket order placed successfully: {api_response.data.order_id}")
            return api_response.data.order_id

        except upstox_client.ApiException as e:
            logging.error(f"Error placing bracket order: {e.body}")
            return None
        except Exception as e:
            logging.error(f"An unexpected error occurred while placing bracket order: {e}")
            return None

if __name__ == '__main__':
    # This is for demonstration. To run this, you need a valid access token.
    # from upstox_auth import get_access_token
    # access_token = get_access_token()
    # if access_token:
    #     order_manager = OrderManager(access_token)
    #     # Replace with a real instrument key and price
    #     order_manager.place_bracket_order("NSE_EQ|INE002A01018", 2500, 2530, 2425) # 1.2% SL, 3% Target
    pass
