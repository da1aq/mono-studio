import os
import requests
from dotenv import load_dotenv

load_dotenv()

token = os.getenv("BOT_TOKEN")

public_url = "https://denial-outsmart-unholy.ngrok-free.dev"

response = requests.post(
    f"https://api.telegram.org/bot{token}/setWebhook",
    data={
        "url": public_url + "/telegram"
    }
)

print(response.json())