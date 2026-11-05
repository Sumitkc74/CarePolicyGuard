import json

with open("scripts/mcd_check_results.json", "r", encoding="utf-8") as f:
    data = json.load(f)

print(f"Total checked: {len(data)}\n")
for d in data:
    slug = d["slug"]
    cms_id = d["cms_id"]
    status = "INVALID" if d["is_invalid"] else (f"HTTP {d['http_status']}" if d["http_status"] == 200 else str(d["error"]))
    doc_t = d.get("doc_title") or d.get("page_title")
    print(f"[{slug}]")
    print(f"  Cited CMS ID: {cms_id}")
    print(f"  Status: {status}")
    print(f"  MCD Title: {doc_t}")
    print(f"  Policy Subject: {d['title']}")
    print()

