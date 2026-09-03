import requests
BASE = "http://127.0.0.1:8000"
# admin token
r = requests.post(f"{BASE}/api/auth/login", json={"account": "adm02test", "password": "Test@123456"})
tok = r.json().get("data", {}).get("access_token") or ""
H = {"Authorization": f"Bearer {tok}"}
tests = [
    ("GET", "/api/knowledge/partitions", H),
    ("GET", "/api/recommend/next", H),
    ("GET", "/api/mindmap/me/1", H),
    ("GET", "/health/detail", None),
    ("GET", "/api/study/sessions", H),
]
for method, path, headers in tests:
    try:
        r = requests.request(method, BASE + path, headers=headers, timeout=20)
        body = r.text[:150].replace("\n", " ")
        print(f"[{r.status_code}] {method} {path} -> {body}")
    except Exception as e:
        print(f"[NETERR] {method} {path} -> {type(e).__name__}")