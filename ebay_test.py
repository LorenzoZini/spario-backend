import os
import base64
import requests
from dotenv import load_dotenv

load_dotenv()

client_id = os.getenv("EBAY_CLIENT_ID")
client_secret = os.getenv("EBAY_CLIENT_SECRET")

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

print("Status:", response.status_code)
print(response.json())