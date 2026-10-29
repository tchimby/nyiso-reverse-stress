"""Build the single-file version of the UI for a host that allows only inline scripts (no relative <script src>).

Usage: python -E -P scripts/build_artifact_page.py OUT.html
Inlines ui/engine.js, drops the html/head/body wrapper, adds the three-state theme tokens and the page gutter.
Data files (ui/data/*.json) and ui/media/* are published next to the page and fetched by relative URL.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
t = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
eng = (ROOT / "ui" / "engine.js").read_text(encoding="utf-8")
t = t.replace('<script src="engine.js"></script>', "<script>\n" + eng + "\n</script>")
t = re.sub(r"<!doctype html>\s*<html[^>]*>\s*<head>\s*<meta charset=\"utf-8\">\s*<meta name=\"viewport\"[^>]*>\s*", "", t)
t = re.sub(r"</head>\s*<body>\s*", "", t)
t = re.sub(r"</body>\s*</html>\s*", "", t)
t = t.replace("<title>NYISO Reverse Stress</title>", "<title>NYISO Reverse Stress</title>\n<meta name=\"claude:viewport-fit-sides\" content=\"cover\">", 1)
i, j = t.index(":root{--bg"), t.index("*{box-sizing")
light = re.search(r":root\{(--bg[^}]*)\}", t[i:j]).group(1)
dark = re.search(r"@media \(prefers-color-scheme:dark\)\{:root\{([^}]*)\}\}", t[i:j]).group(1)
t = t[:i] + f":root{{{light}}}\n@media (prefers-color-scheme:dark){{:root:not([data-theme=\"light\"]){{{dark};color-scheme:dark}}}}\n:root[data-theme=\"dark\"]{{{dark};color-scheme:dark}}\n" + t[j:]
t = t.replace("font:15px/1.55 system-ui,Segoe UI,sans-serif}", "font:15px/1.55 system-ui,Segoe UI,sans-serif;padding-block:8px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}", 1)
t = t.replace("header{padding:20px 16px 4px;", "header{padding:20px 0 4px;").replace("padding:0 16px;display:flex;gap:6px", "padding:0;display:flex;gap:6px").replace("main{max-width:1100px;margin:auto;padding:4px 16px 56px}", "main{max-width:1100px;margin:auto;padding:4px 0 56px}")
t = t.replace("table{border-collapse", "table{display:block;overflow-x:auto;border-collapse", 1)
Path(sys.argv[1]).write_text(t, encoding="utf-8")
print("built", sys.argv[1], len(t))
