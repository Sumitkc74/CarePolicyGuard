import json
import re
import urllib.request
import urllib.error
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICIES_DIR = REPO_ROOT / "app" / "data" / "policies_extended"

policy_files = sorted([f for f in POLICIES_DIR.glob("*.json") if f.stem.startswith(("LCD-", "NCD-", "OPD-"))])

results = []

for pf in policy_files:
    with open(pf, "r", encoding="utf-8") as f:
        data = json.load(f)
    slug = data.get("policy_id")
    title = data.get("title")
    cms_ref = data.get("cms_reference") or {}
    url = cms_ref.get("url")
    cms_id = cms_ref.get("real_cms_id")
    gov_title = cms_ref.get("document_title")

    record = {
        "slug": slug,
        "title": title,
        "cms_id": cms_id,
        "gov_title": gov_title,
        "url": url,
        "http_status": None,
        "final_url": None,
        "page_title": None,
        "doc_title": None,
        "contractor": None,
        "is_invalid": False,
        "error": None
    }

    if not url:
        record["error"] = "No URL"
        results.append(record)
        continue

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            record["http_status"] = resp.status
            record["final_url"] = resp.geturl()
            html = resp.read().decode("utf-8", errors="ignore")

            if "search.aspx?error=Invalid" in record["final_url"] or "Invalid LCD Version" in html or "Invalid NCD" in html:
                record["is_invalid"] = True

            # Extract title tag
            tm = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
            if tm:
                record["page_title"] = " ".join(tm.group(1).split())

            # Look for doc title in h1, h2, or title spans
            # In MCD: <span id="lblDocTitle"> or <h1 id="lblDocTitle"> or class="doc-title"
            dt_match = re.search(r'id=["\'][^"\']*lblDocTitle[^"\']*["\'][^>]*>(.*?)</span>', html, re.I | re.S)
            if not dt_match:
                dt_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.I | re.S)
            if not dt_match:
                dt_match = re.search(r'<h2[^>]*>(.*?)</h2>', html, re.I | re.S)
            if dt_match:
                clean_dt = re.sub(r'<[^>]+>', '', dt_match.group(1))
                record["doc_title"] = " ".join(clean_dt.split())

            # Look for contractor / jurisdiction
            c_match = re.search(r'Contractor Name</span>\s*<span[^>]*>(.*?)</span>', html, re.I | re.S)
            if not c_match:
                c_match = re.search(r'Contractor:\s*<span[^>]*>(.*?)</span>', html, re.I | re.S)
            if not c_match:
                c_match = re.search(r'Contractor Information.*?<td[^>]*>(.*?)</td>', html, re.I | re.S)
            if c_match:
                clean_c = re.sub(r'<[^>]+>', '', c_match.group(1))
                record["contractor"] = " ".join(clean_c.split())

    except urllib.error.HTTPError as e:
        record["http_status"] = e.code
        record["error"] = f"HTTPError {e.code}"
    except Exception as e:
        record["error"] = str(e)

    results.append(record)
    stat = "INVALID" if record["is_invalid"] else (f"HTTP {record['http_status']}" if record["http_status"] else str(record["error"]))
    dt_display = str(record.get("doc_title") or record.get("page_title") or "")[:45]
    print(f"[{slug}] {cms_id} -> {stat} | {dt_display}", flush=True)
    time.sleep(0.2)  # courteous rate limit to cms.gov

with open(REPO_ROOT / "scripts" / "mcd_check_results.json", "w", encoding="utf-8") as out:
    json.dump(results, out, indent=2)

print("\nDone checking 42 policies.", flush=True)
