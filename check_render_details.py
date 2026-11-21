import requests
import json

RENDER_API_KEY = "rnd_6lXCX3FRhzXbymQZVmjSQJjFeY9J"
headers = {
    "Authorization": f"Bearer {RENDER_API_KEY}",
    "Accept": "application/json"
}

SERVICE_ID = "srv-dc0pf5ec6qcc73f2i1r0"

# 1. Check current env vars
resp = requests.get(f"https://api.render.com/v1/services/{SERVICE_ID}/env-vars", headers=headers)
print("Current Env Vars Status:", resp.status_code)
print("Env Vars:", resp.text)

# 2. Check latest deploy status
resp_deploy = requests.get(f"https://api.render.com/v1/services/{SERVICE_ID}/deploys?limit=2", headers=headers)
print("\nDeploys Status:", resp_deploy.status_code)
print("Deploys:", json.dumps(resp_deploy.json(), indent=2))
