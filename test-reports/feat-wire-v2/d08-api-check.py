# -*- coding: utf-8 -*-
"""#8 API 级验证：admin/student 会话列表均只含本人会话"""
import json
import urllib.request


def login(account):
    req = urllib.request.Request(
        "http://127.0.0.1:9988/api/auth/login",
        data=json.dumps({"account": account, "password": "Test@123456"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=10).read())["data"]["access_token"]


def sessions(token):
    req = urllib.request.Request(
        "http://127.0.0.1:9988/api/chat/sessions?limit=50",
        headers={"Authorization": "Bearer " + token},
    )
    return json.loads(urllib.request.urlopen(req, timeout=10).read())["data"]


for account in ["adm02test", "user000001"]:
    tok = login(account)
    lst = sessions(tok)
    ids = sorted({s["user_id"] for s in lst})
    print(account, "sessions:", len(lst), "owner user_ids:", ids)

print("isolation check done: owner sets above must each be a single user_id")
