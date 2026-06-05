import json, urllib.request, ssl
ctx = ssl.create_default_context()
req = urllib.request.Request(
    "http://localhost:8000/api/query",
    data=json.dumps({"question":"电子信息行业的上游涉及哪些企业？","chat_id":"test"}).encode(),
    headers={"Content-Type":"application/json"}
)
resp = urllib.request.urlopen(req, context=ctx)
d = json.loads(resp.read())
print("答案:", d["answer"][:100])
print("来源数:", len(d["sources"]))
for s in d["sources"][:3]:
    print(f"  {s['section_title']}: {s['content'][:60]}")