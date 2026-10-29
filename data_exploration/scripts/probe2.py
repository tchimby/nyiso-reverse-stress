import sys, re, time, requests
out = sys.argv[1]
H = {"User-Agent": "Mozilla/5.0 (student research; polite, 1 req/s)"}
def get(u, **k):
    r = requests.get(u, headers=H, timeout=40, **k); time.sleep(1.1); return r
# 1 dataminer2 bundle: look for endpoint structure only
r = get("https://dataminer2.pjm.com/main.8714799d134cb4fe490e.bundle.js")
print("bundle", r.status_code, len(r.content))
t = r.text
open(out + "/dm2_main_bundle.js", "w", encoding="utf-8").write(t)
for m in sorted(set(re.findall(r'https?://[A-Za-z0-9./_\-]*pjm[A-Za-z0-9./_\-]*', t)))[:40]:
    print("  url:", m)
for m in re.finditer(r'(Ocp-Apim[A-Za-z\-]*|subscription-key|api/v1|/api/|apiUrl|publicApi)', t):
    s = max(0, m.start() - 60); print("  ctx:", re.sub(r"[A-Fa-f0-9]{32}", "<HEX32-REDACTED>", t[s:m.end() + 80].replace("\n", " ")))
    break
# 2 keyless probe of likely public JSON endpoints (no key sent)
for u in ["https://api.pjm.com/api/v1/rt_hrl_lmps?rowCount=2&startRow=1",
          "https://dataminer2.pjm.com/api/v1/da_hrl_lmps?rowCount=2",
          "https://dataminer2.pjm.com/feed/da_hrl_lmps.json",
          "https://dataminer2.pjm.com/feed/da_hrl_lmps/export?format=csv"]:
    try:
        r = get(u); print(r.status_code, r.headers.get("content-type"), len(r.content), u, r.text[:150].replace("\n", " "))
    except Exception as e: print("ERR", u, e)
# 3 dataviewer: CSV export links?
r = get("https://dataviewer.pjm.com/dataviewer/pages/public/lmp.jsf")
t = r.text
for m in sorted(set(re.findall(r'(?:csv|export|download|xls)[^"\' <>]{0,80}', t, re.I)))[:15]: print("  dv:", m)
# 4 monthly report page text
r = get("https://www.pjm.com/markets-and-operations/energy/real-time/monthlylmp.aspx")
txt = re.sub(r"<script.*?</script>|<style.*?</style>", "", r.text, flags=re.S)
txt = re.sub(r"<[^>]+>", " ", txt); txt = re.sub(r"\s+", " ", txt)
i = txt.find("Hourly Real-Time")
print("monthly page:", txt[i:i + 900])
# 5 Monitoring Analytics 2025 page: file types
r = get("https://www.monitoringanalytics.com/reports/PJM_State_of_the_Market/2025.shtml")
print("MA2025", r.status_code)
print(sorted(set(re.findall(r'href="([^"]+\.(?:xlsx?|csv|zip))"', r.text)))[:20])
print(sorted(set(re.findall(r'href="([^"]+\.pdf)"', r.text)))[:40])
