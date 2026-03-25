import sys
import json
import time
import requests
import urllib3
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

print("Python:", sys.version)
print("Starting...")

BASE_URL = "https://mops.twse.com.tw"
KEYWORD = "\u7121\u64d4\u4fdd\u8f49\u63db\u516c\u53f8\u50b5"
DATA_FILE = "data.json"
KEEP_MONTHS = 3

def get_roc_year():
    return datetime.now().year - 1911

def roc_date_to_datetime(roc_str):
    try:
        parts = roc_str.strip().split("/")
        if len(parts) == 3:
            year = int(parts[0]) + 1911
            return datetime(year, int(parts[1]), int(parts[2]))
    except:
        pass
    return None

def decode_response(resp):
    """Try utf-8 first, fallback to big5"""
    for enc in ["utf-8", "big5", "cp950"]:
        try:
            text = resp.content.decode(enc)
            return text
        except:
            continue
    return resp.text

def search_market(market_type, year):
    kind = "L" if market_type == "sii" else "O"
    market_label = "\u4e0a\u5e02" if market_type == "sii" else "\u4e0a\u6ac3"
    print("Searching:", market_label, "year:", year)

    api_url = BASE_URL + "/mops/api/redirectToOld"
    payload = {
        "apiName": "ajax_t51sb10",
        "parameters": {
            "r1": "1",
            "keyWord": KEYWORD,
            "keyWord2": "",
            "year": str(year),
            "Orderby": "1",
            "KIND": kind,
            "CODE": "",
            "Condition2": "1",
            "month1": "0",
            "begin_day": "",
            "end_day": "",
            "encodeURIComponent": 1,
            "step": "1",
            "Stp": 4,
            "firstin": True,
            "off": 1,
            "go": False
        }
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Referer": BASE_URL + "/mops/",
        "Origin": BASE_URL,
    }

    try:
        resp = requests.post(api_url, json=payload, headers=headers, timeout=30, verify=False)
        data = resp.json()
        print("  Step1 HTTP:", resp.status_code, "message:", data.get("message", ""))
    except Exception as e:
        print("  Step1 ERROR:", e)
        return []

    if data.get("code") != 200:
        print("  Step1 failed:", data)
        return []

    old_url = data.get("result", {}).get("url", "")
    if not old_url:
        print("  No redirect URL found")
        return []

    try:
        resp2 = requests.get(old_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": BASE_URL + "/mops/",
        }, timeout=30, verify=False)
        text = decode_response(resp2)
        print("  Step2 HTTP:", resp2.status_code, "length:", len(text))
    except Exception as e:
        print("  Step2 ERROR:", e)
        return []

    if "\u67e5\u7121\u8cc7\u6599" in text:
        print("  No data found for this query")
        return []

    soup = BeautifulSoup(text, "html.parser")
    table = soup.find("table", {"class": "hasBorder"}) or soup.find("table")
    if not table:
        print("  No table found. Preview:", text[:300])
        return []

    results = []
    rows = table.find_all("tr")[1:]
    print("  Rows found:", len(rows))

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        date_str = cells[0].get_text(strip=True)
        code     = cells[1].get_text(strip=True)
        name     = cells[2].get_text(strip=True)
        subject  = cells[3].get_text(strip=True)
        link_tag = cells[3].find("a")
        href = ""
        if link_tag and link_tag.get("href"):
            h = link_tag["href"]
            href = h if h.startswith("http") else BASE_URL + h

        results.append({
            "\u80a1\u7968\u4ee3\u78bc": code,
            "\u516c\u53f8\u540d\u7a31": name,
            "\u5e02\u5834\u5225": market_label,
            "\u516c\u544a\u65e5\u671f": date_str,
            "\u516c\u544a\u4e3b\u65e8": subject,
            "\u516c\u544a\u9023\u7d50": href,
        })

    print("  Records:", len(results))
    return results

def load_existing():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("records", [])
    except:
        return []

def merge_and_dedupe(old_records, new_records):
    seen = set()
    merged = []
    for r in new_records + old_records:
        key = (r.get("\u80a1\u7968\u4ee3\u78bc", ""), r.get("\u516c\u544a\u65e5\u671f", ""), r.get("\u516c\u544a\u4e3b\u65e8", "")[:20])
        if key not in seen:
            seen.add(key)
            merged.append(r)
    return merged

def filter_last_n_months(records, months=3):
    cutoff = datetime.now() - timedelta(days=months * 31)
    kept = []
    for r in records:
        d = roc_date_to_datetime(r.get("\u516c\u544a\u65e5\u671f", ""))
        if d is None or d >= cutoff:
            kept.append(r)
    return kept

def main():
    year = get_roc_year()
    print("ROC Year:", year)

    new_records = []
    for market in ["sii", "otc"]:
        new_records += search_market(market, year)
        time.sleep(2)

    now = datetime.now()
    if now.month <= 3:
        print("\nAlso fetching previous year...")
        for market in ["sii", "otc"]:
            new_records += search_market(market, year - 1)
            time.sleep(2)

    print("\nMerging with existing records...")
    old_records = load_existing()
    print("  Existing records:", len(old_records))
    merged = merge_and_dedupe(old_records, new_records)
    print("  After merge:", len(merged))

    filtered = filter_last_n_months(merged, KEEP_MONTHS)
    print("  After 3-month filter:", len(filtered))

    filtered.sort(key=lambda r: r.get("\u516c\u544a\u65e5\u671f", ""), reverse=True)

    output = {
        "year": year,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M UTC+8"),
        "keyword": KEYWORD,
        "keep_months": KEEP_MONTHS,
        "total": len(filtered),
        "records": filtered,
    }

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("\nDone! Records:", len(filtered), "->", DATA_FILE)

main()
