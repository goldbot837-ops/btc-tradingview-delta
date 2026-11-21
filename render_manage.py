import requests
import json

RENDER_API_KEY = "rnd_6lXCX3FRhzXbymQZVmjSQJjFeY9J"
headers = {
    "Authorization": f"Bearer {RENDER_API_KEY}",
    "Accept": "application/json"
}

resp = requests.get("https://api.render.com/v1/services", headers=headers)
print("Status Code:", resp.status_code)
if resp.ok:
    services = resp.json()
    print(f"Total services found: {len(services)}")
    for s in services:
        service_data = s.get("service", {})
        print("ID:", service_data.get("id"))
        print("Name:", service_data.get("name"))
        print("Type:", service_data.get("type"))
        print("Repo:", service_data.get("repo"))
        print("Service Details:", json.dumps(service_data, indent=2))
else:
    print("Error:", resp.text)
