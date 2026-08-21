import os

import requests

API_KEY = os.getenv("SOTONGPT_API_KEY")
HEADERS = {"Authorization": f"Bearer {API_KEY}"}
GROUP_ID = "f7bbdf36-e772-4c6d-b58b-60715ef935ed"

response = requests.post(
    f"https://sotongpt.soton.ac.uk/api/v1/groups/id/{GROUP_ID}/users", headers=HEADERS
)

users = response.json()
emails = [user["email"] for user in users]
print(emails)
print(len(emails), "users returned")
