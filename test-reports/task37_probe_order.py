# -*- coding: utf-8 -*-
import json, urllib.request, urllib.error
BASE="http://127.0.0.1:8000"
OP=urllib.request.build_opener(urllib.request.ProxyHandler({}))

def api(method,path,body=None,token=None,headers=None):
    data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None
    req=urllib.request.Request(BASE+path,data=data,method=method)
    req.add_header("Content-Type","application/json")
    if token: req.add_header("Authorization",f"Bearer {token}")
    for k,v in (headers or {}).items(): req.add_header(k,v)
    try:
        with OP.open(req,timeout=20) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return -1, repr(e)

s,j=api("POST","/api/auth/login",{"account":"adm02test","password":"Test@123456"})
tok=(json.loads(j).get("data") or {}).get("access_token")
print("login", s, "token?", bool(tok))

# probe cadidates list
for cid in (3,1,2,4,5):
    s,j=api("GET",f"/api/cohorts/{cid}",token=tok)
    if s==200:
        print("cohort",cid,"status",s)
        cj=json.loads(j)
        c=cj.get("data",{}).get("cohort") if isinstance(cj.get("data"),dict) else {}
        print("  yr", c.get("yn"), "cur", c.get("current_student_count"), "max", c.get("max_student_count"),"series_id",c.get("series_id"))
    else:
        print("cohort",cid,"status",s, j[:120])

# try order create on candidate (series2, cohort5)
import time
for (sid,cid) in ((2,4),(2,5)):
    s,j=api("POST","/api/trade/order",{"series_id":sid,"cohort_id":cid,"coupon_id":None},token=tok,headers={"Idempotency-Key":f"probe-{int(time.time()*1000)}"})
    print("order_create",sid,cid,s, j[:400])

# list orders
s,j=api("GET","/api/trade/orders?page=1&page_size=3",token=tok)
print("order_list", s, j[:600])

# detail of first order
if s==200:
    items=(json.loads(j).get("data") or {}).get("items") or []
    if items:
        on=items[0].get("order_no")
        s2,j2=api("GET",f"/api/trade/order/{on}",token=tok)
        print("order_detail",on,s2, j2[:600])