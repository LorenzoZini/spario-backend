import os
import base64
import requests
from dotenv import load_dotenv

load_dotenv()

client_id = os.getenv("EBAY_CLIENT_ID")
client_secret = os.getenv("EBAY_CLIENT_SECRET")

# OAuth Token
credentials = f"{client_id}:{client_secret}"
encoded_credentials = base64.b64encode(credentials.encode()).decode()

token_url = "https://api.sandbox.ebay.com/identity/v1/oauth2/token"

headers = {
    "Content-Type": "application/x-www-form-urlencoded",
    "Authorization": f"Basic {encoded_credentials}",
}

data = {
    "grant_type": "client_credentials",
    "scope": "https://api.ebay.com/oauth/api_scope",
}

response = requests.post(token_url, headers=headers, data=data)

access_token = response.json()["access_token"]

print("Access token ottenuto!")

# Search Product
search_url = "https://api.sandbox.ebay.com/buy/browse/v1/item_summary/search"

search_headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json",
}

params = {
    "q": "PlayStation 5 Slim",
    "limit": 5,
}

search_response = requests.get(
    search_url,
    headers=search_headers,
    params=params
)

results = search_response.json()

print(results)