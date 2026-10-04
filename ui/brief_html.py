"""Printable one-page Desk Brief as a self-contained HTML document (white paper, black text, so it
prints cleanly). Every sentence it contains is passed in from analytics.desk_brief."""

from html import escape

LABEL = "Rules-based, not a forecast"


def _ul(items: list[str], tag: str = "ul") -> str:
    if not items:
        return "<p>None.</p>"
    return f"<{tag}>" + "".join(f"<li>{escape(s)}</li>" for s in items) + f"</{tag}>"


def brief_html(title: str, generated: str, lookback: str, funding: list[str], movers: list[str],
               stretched: list[str], table_rows: list[dict], skipped: list[str],
               sources: list[str]) -> str:
    head = ("<tr>" + "".join(f"<th>{escape(c)}</th>" for c in table_rows[0]) + "</tr>"
            if table_rows else "")
    body = "".join("<tr>" + "".join(f"<td>{escape(str(v))}</td>" for v in r.values()) + "</tr>"
                   for r in table_rows)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{escape(title)}</title>
<style>
@page {{ size: A4; margin: 10mm; }}
body {{ font: 10.5px/1.35 Consolas, "Cascadia Mono", monospace; color: #000; background: #fff;
       margin: 0 auto; max-width: 190mm; }}
h1 {{ font-size: 15px; margin: 0 0 2px; }} h2 {{ font-size: 12px; margin: 8px 0 2px; }}
.label {{ font-weight: bold; border: 1.5px solid #000; padding: 1px 5px; display: inline-block; }}
ul {{ margin: 2px 0 2px 16px; padding: 0; }} li {{ margin: 0 0 1px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 9px; }}
th, td {{ border: 1px solid #888; padding: 1px 3px; text-align: right; }}
th:nth-child(-n+3), td:nth-child(-n+3) {{ text-align: left; }}
.small {{ font-size: 8.5px; color: #333; }}
</style></head><body>
<h1>{escape(title)}</h1>
<p><span class="label">{LABEL.upper()}</span> Generated {escape(generated)} from the app's official
data. History window: {escape(lookback)}. Statistics are descriptive only.</p>
<h2>Funding conditions</h2>{_ul(funding)}
<h2>Largest movers (by |change z|)</h2>{_ul(movers, "ol")}
<h2>Stretched (beyond 2 SD)</h2>{_ul(stretched)}
<h2>All series</h2><table>{head}{body}</table>
<p class="small">Not available: {escape(' '.join(skipped)) if skipped else 'none'}</p>
<p class="small">Sources: {escape('; '.join(sources))}</p>
</body></html>"""
