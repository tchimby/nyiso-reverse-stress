"""Render the deck sources (deck.json + slides/*.html) into one printable HTML, one 1920x1080 page per slide."""
import json, re, sys
from pathlib import Path

src = Path(sys.argv[1]); out = Path(sys.argv[2])
deck = json.loads((src / "deck.json").read_text(encoding="utf-8"))
blobs = {"9d2be104e07e8917df4c81a2685527df": "pnl_waterfall.png",
         "5586fd35be1ae7f9553280a98c60ce99": "corr_by_season.png",
         "e880865513a4a8838b1130063207ee2f": "demo_tour.gif"}
parts = []
for sid in deck["order"]:
    t = (src / "slides" / f"{sid}.html").read_text(encoding="utf-8")
    for k, v in blobs.items():
        t = t.replace(f"/_blob/{k}", v)
    t = re.sub(r"<aside>.*?</aside>", "", t, flags=re.S)
    parts.append(t)
links = "".join(f'<link rel="stylesheet" href="{f["href"]}">' for f in deck["faces"].values())
css = """
@page{size:1920px 1080px;margin:0}
html,body{margin:0;padding:0;background:#fff}
section{width:1920px;height:1080px;position:relative;box-sizing:border-box;overflow:hidden;page-break-after:always;break-after:page}
section *{box-sizing:border-box;margin:0}
h1,h2,h3{font-weight:600}h1{font-size:96px;line-height:1.1}h2{font-size:64px;line-height:1.15}h3{font-size:44px;line-height:1.2}
p{font-size:32px;line-height:1.4}ul,ol{line-height:1.4}li{padding-left:4px}
div:not([style*="display:flex"]):not([style*="display:grid"]){display:flex;flex-direction:column}
table{border-collapse:collapse}th,td{padding:0.35em 0.6em;border:1px solid #c9c4b8;text-align:left;vertical-align:top}th{font-weight:600}
x-shape{display:block;flex-shrink:0}
x-shape[kind=rounded]{border-radius:8px}x-shape[kind=ellipse]{border-radius:50%}
x-shape[kind=arrow-right]{clip-path:polygon(0 30%,60% 30%,60% 0,100% 50%,60% 100%,60% 70%,0 70%)}
x-shape[kind=arrow-left]{clip-path:polygon(100% 30%,40% 30%,40% 0,0 50%,40% 100%,40% 70%,100% 70%)}
img{display:block}
"""
out.write_text(f"<!doctype html><html><head><meta charset='utf-8'><title>{deck['title']}</title>{links}<style>{css}</style></head><body>{''.join(parts)}</body></html>", encoding="utf-8")
print("slides:", len(parts))
