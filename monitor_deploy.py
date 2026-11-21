import requests
import json
import time

RENDER_API_KEY = "rnd_6lXCX3FRhzXbymQZVmjSQJjFeY9J"
SERVICE_ID = "srv-dc0pf5ec6qcc73f2i1r0"

headers = {
    "Authorization": f"Bearer {RENDER_API_KEY}",
    "Accept": "application/json"
}

resp = requests.get(f"https://api.render.com/v1/services/{SERVICE_ID}/deploys?limit=2", headers=headers)
deploys = resp.json()
latest_deploy = deploys[0]["deploy"]
print("Latest Deploy ID:", latest_deploy["id"])
print("Status:", latest_deploy["status"])
print("Commit:", latest_deploy["commit"]["message"])

deploy_id = latest_deploy["id"]
for i in range(30):
    time.sleep(5)
    check = requests.get(f"https://api.render.com/v1/services/{SERVICE_ID}/deploys/{deploy_id}", headers=headers)
    if check.ok:
        st = check.json().get("status")
        print(f"[{i*5}s] Status: {st}")
        if st in ["live", "succeeded"]:
            print("===> DEPLOY SUCCESSFUL! Service is LIVE!")
            break
        elif st in ["build_failed", "update_failed", "canceled"]:
            print("===> Deploy failed:", check.text)
            break
