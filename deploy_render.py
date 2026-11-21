import requests
import json
import time

RENDER_API_KEY = "rnd_6lXCX3FRhzXbymQZVmjSQJjFeY9J"
SERVICE_ID = "srv-dc0pf5ec6qcc73f2i1r0"

headers = {
    "Authorization": f"Bearer {RENDER_API_KEY}",
    "Accept": "application/json",
    "Content-Type": "application/json"
}

# 1. Update startCommand on Render
patch_payload = {
    "serviceDetails": {
        "envSpecificDetails": {
            "startCommand": "gunicorn main:app --bind 0.0.0.0:$PORT"
        }
    }
}
resp_patch = requests.patch(f"https://api.render.com/v1/services/{SERVICE_ID}", headers=headers, json=patch_payload)
print("Patch Service Status:", resp_patch.status_code)
print("Patch Response:", resp_patch.text)

# If serviceDetails didn't accept nested, try top level:
if not resp_patch.ok:
    resp_patch = requests.patch(f"https://api.render.com/v1/services/{SERVICE_ID}", headers=headers, json={"startCommand": "gunicorn main:app --bind 0.0.0.0:$PORT"})
    print("Top-level Patch Status:", resp_patch.status_code)
    print("Top-level Patch Response:", resp_patch.text)

# 2. Trigger new deploy
deploy_payload = {
    "clearCache": "clear"
}
resp_deploy = requests.post(f"https://api.render.com/v1/services/{SERVICE_ID}/deploys", headers=headers, json=deploy_payload)
print("\nTrigger Deploy Status:", resp_deploy.status_code)
deploy_data = resp_deploy.json()
print("Deploy Data:", json.dumps(deploy_data, indent=2))
deploy_id = deploy_data.get("id")

# 3. Poll deploy status until live
if deploy_id:
    print(f"\nMonitoring deploy {deploy_id}...")
    for _ in range(30):
        time.sleep(5)
        check = requests.get(f"https://api.render.com/v1/services/{SERVICE_ID}/deploys/{deploy_id}", headers=headers)
        if check.ok:
            st = check.json().get("status")
            print(f"Deploy status: {st}")
            if st in ["live", "succeeded"]:
                print("===> DEPLOY SUCCESSFUL! Service is LIVE!")
                break
            elif st in ["build_failed", "update_failed", "canceled"]:
                print("===> Deploy failed:", check.text)
                break
