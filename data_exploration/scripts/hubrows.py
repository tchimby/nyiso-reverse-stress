import sys, re, os, fitz
d = sys.argv[1]
for fn, pg in [("2022-som-pjm-sec3.pdf", 48), ("2025q1-som-pjm-sec3.pdf", 57)]:
    t = fitz.open(os.path.join(d, fn))[pg - 1].get_text()
    t = re.sub(r"\s+", " ", t)
    print(fn, "p", pg)
    print(t[:1800])
