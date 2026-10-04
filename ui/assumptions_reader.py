"""Read assumptions.py: every top-level constant with its comment, source and status.

Status comes from the comment text, so assumptions.py stays the single source of truth:
  VERIFIED     comment contains "Verified" (checked against the cited rule text)
  UNVERIFIED   comment contains "UNVERIFIED", or cites a public source not re-checked here
  n/a          own assumption or hypothetical value (nothing to verify)
"""

import ast
import pathlib
import re

import pandas as pd

PATH = pathlib.Path(__file__).resolve().parent.parent / "assumptions.py"
_HYPOTHETICAL_MARKER = "Step 3: stress"


def _comment_block(lines: list[str], lineno: int) -> list[str]:
    """Contiguous comment lines directly above line `lineno` (1-based), skipping rulers."""
    out = []
    i = lineno - 2
    while i >= 0 and lines[i].lstrip().startswith("#"):
        text = lines[i].strip().lstrip("#").strip()
        if not re.fullmatch(r"[-=\s]*", text) and not text.startswith("---"):
            out.insert(0, text)
        i -= 1
    return out


def _inline_comment(line: str) -> str:
    # Values here never contain '#', so the first '#' starts the comment.
    return line.split("#", 1)[1].strip() if "#" in line else ""


def _type_and_status(text: str, hypothetical: bool) -> tuple[str, str]:
    if "UNVERIFIED" in text:
        return ("Regulatory / public" if re.search(r"PRA|Basel|BoE|Bank of England|HMRC|LCR|Art \d", text)
                else "Own assumption", "UNVERIFIED")
    if "Verified" in text:
        return "Regulatory", "VERIFIED"
    if re.search(r"\bpublic\b", text, re.I):
        return "Public source", "UNVERIFIED"
    if hypothetical or "HYPOTHETICAL" in text or "hypothetical" in text:
        return "Hypothetical", "n/a"
    return "Own assumption", "n/a"


def read_assumptions(path: pathlib.Path = PATH) -> pd.DataFrame:
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    marker = next((i + 1 for i, l in enumerate(lines) if _HYPOTHETICAL_MARKER in l), None)
    # The stress section ends at the next "# ====" section ruler after its own header block,
    # so later sections (Desk Brief, Replay, Forecast Lab...) are not tagged hypothetical.
    end = next((i + 1 for i, l in enumerate(lines)
                if marker is not None and i + 1 > marker + 2 and l.startswith("# ====")),
               len(lines) + 1)
    rows = []
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign) or not isinstance(node.targets[0], ast.Name):
            continue
        name = node.targets[0].id
        comment = " ".join(_comment_block(lines, node.lineno)
                           + [_inline_comment(lines[node.lineno - 1])]).strip()
        value = ast.get_source_segment(source, node.value) or ""
        value = "\n".join(line.split("#", 1)[0] for line in value.splitlines())  # drop comments
        value = re.sub(r"\s+", " ", value).replace("{ ", "{").replace(", }", "}")
        hypothetical = (marker is not None and marker < node.lineno < end
                        and name != "MONTH_DAYS")
        kind, status = _type_and_status(comment, hypothetical and "own assumption" not in
                                        comment.lower())
        rows.append({"Name": name, "Value": value if len(value) <= 120 else value[:117] + "...",
                     "Type": kind, "Status": status, "Source / comment": comment})
    return pd.DataFrame(rows)
