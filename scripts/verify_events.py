"""Fetch every event's official page and check the date and phrase appear on it.
Writes data/events_verified.json. Run: .venv\\Scripts\\python scripts\\verify_events.py
"""

import html
import json
import pathlib
import re
import sys
import urllib.request
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.events import EVENTS, VERIFIED_PATH, date_strings  # noqa: E402
from data.markets import USER_AGENT  # noqa: E402


def page_text(url: str) -> tuple[int, str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode("utf-8", "replace")
        status = r.status
    title = re.search(r"<title>(.*?)</title>", raw, re.S)
    raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", raw, flags=re.S)
    text = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw)))
    return status, (html.unescape(title.group(1)).strip() if title else ""), text


def main():
    rows = []
    for e in EVENTS:
        row = {"day": e.day, "region": e.region, "label": e.label, "url": e.url, "phrase": e.phrase,
               "checked_at": datetime.now().isoformat(timespec="seconds")}
        try:
            status, title, text = page_text(e.url)
            date_found = next((d for d in date_strings(e.day) if d in text), None)
            phrase_found = e.phrase.lower() in text.lower()
            row.update({"http": status, "page_title": title[:120], "date_found": date_found,
                        "phrase_found": phrase_found,
                        "verified": status == 200 and bool(date_found) and phrase_found})
        except Exception as ex:
            row.update({"verified": False, "error": f"{type(ex).__name__}: {ex}"})
        rows.append(row)
        print(f"{'OK  ' if row['verified'] else 'FAIL'} {e.day} {e.region} {row.get('date_found')} "
              f"phrase={row.get('phrase_found')} {row.get('page_title', row.get('error', ''))[:70]}")
    VERIFIED_PATH.write_text(json.dumps({"run_at": datetime.now().isoformat(timespec="seconds"),
                                         "events": rows}, indent=1), encoding="utf-8")
    print("wrote", VERIFIED_PATH)


if __name__ == "__main__":
    main()
