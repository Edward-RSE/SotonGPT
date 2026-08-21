# Building a list of users

## Group members

To get a list of all groups, user the `/api/v1/users/groups` endpoint.

```bash
curl -h "Authorization: Bearer API-KEY" https://sotongpt.soton.ac.uk/api/v1/users/groups
```

In the response, you can find the ID of the group you want to get members for, e.g.

```json
[
  {
    "id": "f7bbdf36-e772-4c6d-b58b-60715ef935ed",  // this is the id you want
    "user_id": "7209a752-0efc-4091-8164-0d822fddda9d",
    "name": "Pilot Test",
    "description": "This is the group for members of the pilot test cohort.",
    "data": {
      "config": {
        "share": false
      }
    },
    // ... other data
  }
  // ... other groups
]
```

Then send a query to get the users. Note that this is post for some reason.

```bash
curl -H "Authorization: Bearer API-KEY" -X POST https://sotongpt.soton.ac.uk/api/v1/groups/id/f7bbdf36-e772-4c6d-b58b-60715ef935ed/users
```

The response is a JSON array of user objects for that group, for example:

```json
[
  {
    "id": "3a1c9e2b-...",
    "name": "Jane Doe",
    "email": "jd1e21@soton.ac.uk",
    "role": "user",
    // ... other fields
  }
  // ... other users
]
```

## Combining results across groups

To build a complete list of users across several groups:

1. Fetch the full list of groups.
2. Loop through each group ID and query its members.
3. Merge the results into a single list, de-duplicating by `id` (a user may belong to more than one group).

A minimal example in Python:

```python
import requests

BASE_URL = "https://sotongpt.soton.ac.uk/api/v1"
HEADERS = {"Authorization": "Bearer API-KEY"}

groups = requests.get(f"{BASE_URL}/users/groups", headers=HEADERS).json()

all_users = {}
for group in groups:
    resp = requests.post(f"{BASE_URL}/groups/id/{group['id']}/users", headers=HEADERS)
    for user in resp.json():
        all_users[user["id"]] = user

print(f"Found {len(all_users)} unique users across {len(groups)} groups")
```
