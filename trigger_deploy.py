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

resp_deploy = requests.post(f"https://api.render.com/v1/services/{SERVICE_ID}/deploys", headers=headers, json={"clearCache": "clear"})
print("Trigger Deploy Status:", resp_deploy.status_code)
deploy_data = resp_deploy.json()
deploy_id = deploy_data.get("id")
print("Deploy ID:", deploy_id)

if deploy_id:
    for i in range(40):
        time.sleep(5)
        check = requests.get(f"https://api.render.com/v1/services/{SERVICE_ID}/deploys/{deploy_id}", headers=headers)
        if check.ok:
            st = check.json().get("status")
            print(f"[{i*5}s] Deploy status: {st}")
            if st in ["live", "succeeded"]:
                print("===> DEPLOY SUCCESSFUL! Service is LIVE!")
                break
            elif st in ["build_failed", "update_failed", "canceled"]:
                print("===> Deploy failed:", check.text)
                break
