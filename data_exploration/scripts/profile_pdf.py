import sys, re, glob, os
import fitz
d = sys.argv[1]
for f in sorted(glob.glob(os.path.join(d, "*.pdf"))):
    doc = fitz.open(f)
    print("==", os.path.basename(f), "pages", len(doc))
    hits = 0
    for i, p in enumerate(doc):
        t = p.get_text()
        if re.search(r"(?i)western hub|dominion hub", t) or re.search(r"(?i)elliott|January 2025|polar vortex", t):
            for m in re.finditer(r"(?i)(western hub|dominion hub|winter storm elliott|polar vortex)", t):
                s = re.sub(r"\s+", " ", t[max(0, m.start() - 120):m.end() + 220])
                print(f"  p{i+1}: {s}")
                hits += 1
                break
        if hits > 12: break
    # tables with hourly or daily? count 'Day-ahead' mentions of hubs
    full = " ".join(p.get_text() for p in doc)
    print("  Western Hub mentions:", len(re.findall("Western Hub", full)), " Dominion Hub:", len(re.findall("Dominion Hub", full)),
          " Elliott:", len(re.findall("Elliott", full)))
