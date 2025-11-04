import upstox_client
import webbrowser
import time
import os
import json
from datetime import datetime, date
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from urllib.parse import urlparse, parse_qs, urlencode
from config import API_KEY, API_SECRET, REDIRECT_URI

TOKEN_FILE = "token.json"

def save_token(token):
    """Saves the access token and the current date to a file."""
    data = {
        "access_token": token,
        "date": date.today().isoformat()
    }
    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f)

def load_token():
    """Loads the access token from the file if it's from the current day."""
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            data = json.load(f)
            token_date = datetime.fromisoformat(data["date"]).date()
            if token_date == date.today():
                return data["access_token"]
    return None

def get_access_token():
    """
    Automates the Upstox login process to get the access token.
    Checks for a valid token from the current day before generating a new one.
    """
    # Check for a valid token from the current day
    access_token = load_token()
    if access_token:
        print("Using cached access token for the day.")
        return access_token
    api_version = "v2"
    configuration = upstox_client.Configuration()
    api_client = upstox_client.ApiClient(configuration)
    api_instance = upstox_client.LoginApi(api_client)

    # Manually construct the login URL
    base_url = "https://api.upstox.com"
    endpoint = "/v2/login/authorization/dialog"
    params = {
        "client_id": API_KEY,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code"
    }
    login_url = f"{base_url}{endpoint}?{urlencode(params)}"

    # Use selenium to automate the login
    try:
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.get(login_url)

        # Wait for the user to login and the redirect to happen
        # The user will have to manually enter their credentials and 2FA
        print("Please log in to Upstox in the browser window that has been opened.")

        while REDIRECT_URI not in driver.current_url:
            time.sleep(1)

        # Get the authorization code from the redirected URL
        parsed_url = urlparse(driver.current_url)
        query_params = parse_qs(parsed_url.query)
        code = query_params.get("code", [None])[0]

        if not code:
            raise Exception("Could not get the authorization code.")

        # Close the browser
        driver.quit()

        # Get the access token
        token_response = api_instance.token(
            api_version=api_version,
            code=code,
            client_id=API_KEY,
            client_secret=API_SECRET,
            redirect_uri=REDIRECT_URI,
            grant_type="authorization_code"
        )

        access_token = token_response.access_token

        if not access_token:
            raise Exception("Could not get the access token.")

        print("Access token generated successfully.")
        save_token(access_token)
        return access_token

    except Exception as e:
        print(f"An error occurred during authentication: {e}")
        return None

if __name__ == "__main__":
    access_token = get_access_token()
    if access_token:
        print(f"Access Token: {access_token}")
