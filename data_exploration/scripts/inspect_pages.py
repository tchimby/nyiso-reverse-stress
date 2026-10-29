import sys, re, os, glob
d = sys.argv[1]
for f in sorted(glob.glob(os.path.join(d, "*"))):
    t = open(f, "rb").read().decode("utf-8", "ignore")
    title = re.search(r"<title[^>]*>(.*?)</title>", t, re.S | re.I)
    print("==", os.path.basename(f), len(t), "|", (title.group(1).strip()[:100] if title else None))
    links = set(re.findall(r'href="([^"]+)"', t))
    keep = [l for l in links if re.search(r"lmp|csv|xls|zip|hub|ashx|pricing|state_of|SOM|som|feed|api", l, re.I)]
    for l in sorted(keep)[:40]:
        print("    ", l[:160])
    if "dataminer2" in os.path.basename(f) and "feed" in os.path.basename(f):
        print(t[:1500])
