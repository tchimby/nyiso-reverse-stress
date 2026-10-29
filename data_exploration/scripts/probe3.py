import sys, re, time, requests, importlib
out = sys.argv[1]
H = {"User-Agent": "Mozilla/5.0 (student research; polite, 1 req/s)"}
for m in ["pypdf", "PyPDF2", "fitz", "pdfplumber"]:
    print(m, importlib.util.find_spec(m) is not None)
for u in ["https://www.monitoringanalytics.com/reports/PJM_State_of_the_Market/2022/2022-som-pjm-sec3.pdf",
          "https://www.monitoringanalytics.com/reports/PJM_State_of_the_Market/2025/2025q1-som-pjm-sec3.pdf"]:
    r = requests.get(u, headers=H, timeout=90); time.sleep(1.1)
    print(r.status_code, len(r.content), r.headers.get("content-type"), u)
    if r.status_code == 200 and len(r.content) < 60e6:
        open(out + "/" + u.rsplit("/", 1)[1], "wb").write(r.content)
# terms
for u in ["https://www.pjm.com/about-pjm/legal", "https://www.pjm.com/markets-and-operations/etools/data-miner-2.aspx"]:
    r = requests.get(u, headers=H, timeout=40); time.sleep(1.1)
    txt = re.sub(r"<script.*?</script>|<style.*?</style>", "", r.text, flags=re.S)
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", txt))
    print(r.status_code, u, len(txt))
    for m in re.finditer(r"(?i)(public data|account|redistribut|terms of use|api key|subscription)", txt):
        print("   ...", txt[max(0, m.start() - 150):m.end() + 250]); break
