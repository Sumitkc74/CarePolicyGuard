import json

with open("scripts/mcd_check_results.json", "r", encoding="utf-8") as f:
    data = json.load(f)

for i, d in enumerate(data):
    slug = str(d.get("slug"))
    cms_id = str(d.get("cms_id"))
    stat = "INVALID" if d.get("is_invalid") else (f"HTTP {d['http_status']}" if d.get("http_status") else str(d.get("error")))
    dt = str(d.get("doc_title") or d.get("page_title") or "")[:55]
    print(f"{slug:<22} | {cms_id:<20} | {stat:<10} | {dt}")
