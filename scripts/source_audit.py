"""Live source audit: fetch every series, record raw first lines, parsed result, earliest and
latest date, frequency, terms and status. Writes data/source_audit.json and data/source_audit.md.

Run: .venv\\Scripts\\python scripts\\source_audit.py
"""

import json
import pathlib
import sys
import time
import urllib.request
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data import macro, markets  # noqa: E402

OUT_JSON = ROOT / "data" / "source_audit.json"
OUT_MD = ROOT / "data" / "source_audit.md"

# Sources tried and not usable from this machine (re-tested live by this script).
NOT_USED = [
    ("FRED US Treasury 2y (DGS2)", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS2", "fred"),
    ("FRED US Treasury 10y (DGS10)", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10", "fred"),
    ("Stooq FTSE 100 (^ukx)", "https://stooq.com/q/d/l/?s=%5Eukx&i=d", "stooq"),
]


def record_raw(module):
    """Wrap a module's _get so the first raw response lines are captured."""
    captured = []
    original = module._get
    def wrapper(url, *a, **k):
        body = original(url, *a, **k)
        if not captured:
            text = body if isinstance(body, str) else f"<binary {len(body)} bytes: {body[:8].hex()}>"
            captured.append((url, [l for l in text.splitlines() if l.strip()][:3]))
        return body
    module._get = wrapper
    return captured, lambda: setattr(module, "_get", original)


def audit_series(key: str) -> dict:
    spec = macro.SERIES[key]
    mod = markets if spec.provider == "markets" else macro
    captured, restore = record_raw(mod)
    t = time.time()
    row = {"key": key, "name": spec.name, "provider": spec.provider, "code": spec.code,
           "source": spec.source, "unit": spec.unit, "frequency": spec.frequency,
           "terms": macro.terms_for(spec),
           "terms_unverified": spec.provider in macro.TERMS_UNVERIFIED}
    try:
        s = macro.fetch_live(key)
        row.update({"works": True, "rows": int(len(s)), "earliest": s.index[0].date().isoformat(),
                    "latest": s.index[-1].date().isoformat(), "first_value": float(s.iloc[0]),
                    "last_value": float(s.iloc[-1])})
    except Exception as e:
        row.update({"works": False, "error": f"{type(e).__name__}: {str(e)[:160]}"})
    finally:
        restore()
    row["seconds"] = round(time.time() - t, 1)
    if captured:
        row["url"], row["raw_first_lines"] = captured[0][0], [l[:200] for l in captured[0][1]]
    elif spec.provider == "markets" and markets.SERIES[spec.code].provider == "eia":
        row["url"] = markets.EIA_BRENT_URL
    return row


def audit_not_used(name: str, url: str, kind: str) -> dict:
    t = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": macro.USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as r:
            text = r.read().decode("utf-8", "replace")
        ok = "Date" in text[:50] or "DATE" in text[:50] or "observation_date" in text[:50]
        status = "responded with data" if ok else "responded, but not data (bot challenge / HTML)"
    except Exception as e:
        status = f"failed: {type(e).__name__}: {str(e)[:120]}"
    return {"name": name, "url": url, "status": status, "seconds": round(time.time() - t, 1),
            "kind": kind}


def main():
    started = datetime.now().isoformat(timespec="seconds")
    rows = [audit_series(k) for k in macro.SERIES]
    for r in rows:
        print(f"{r['key']:14s} {'OK ' if r.get('works') else 'FAIL'} {r.get('earliest', '-'):10s} "
              f"{r.get('latest', '-'):10s} {r.get('rows', 0):6d} rows {r['seconds']:5.1f}s "
              f"{r.get('error', '')}")
    not_used = [audit_not_used(*n) for n in NOT_USED]
    for n in not_used:
        print(f"NOT USED {n['name']}: {n['status']}")
    OUT_JSON.write_text(json.dumps({"run_at": started, "series": rows, "not_used": not_used},
                                   indent=1), encoding="utf-8")
    lines = [f"# Source audit\n\nRun live from the development machine at {started} by "
             "`scripts/source_audit.py`. Official public providers only.\n",
             "| Series | Source | Works | Frequency | Earliest | Latest | Rows | Terms |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        terms = ("TERMS UNVERIFIED. " if r["terms_unverified"] else "") + r["terms"]
        lines.append(f"| {r['name']} | {r['source']} | {'yes' if r.get('works') else 'NO: ' + r.get('error', '')} "
                     f"| {r['frequency']} | {r.get('earliest', '-')} | {r.get('latest', '-')} "
                     f"| {r.get('rows', '-')} | {terms} |")
    lines += ["\n## Not used\n", "| Source | URL | Result |", "|---|---|---|"]
    for n in not_used:
        lines.append(f"| {n['name']} | {n['url']} | {n['status']} |")
    lines.append("\n## Raw first lines and parsed result\n")
    for r in rows:
        lines.append(f"### {r['name']}\n\n- URL: {r.get('url', 'n/a')}")
        if r.get("works"):
            lines.append(f"- Parsed: {r['rows']} observations, {r['earliest']} = {r['first_value']}"
                         f" ... {r['latest']} = {r['last_value']} ({r['unit']})")
        else:
            lines.append(f"- FAILED: {r.get('error')}")
        if r.get("raw_first_lines"):
            lines.append("- Raw first lines:\n\n```\n" + "\n".join(r["raw_first_lines"]) + "\n```\n")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote", OUT_JSON, "and", OUT_MD)


if __name__ == "__main__":
    main()
