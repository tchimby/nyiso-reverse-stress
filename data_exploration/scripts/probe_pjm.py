import sys, time, os, requests
out = sys.argv[1]
H = {"User-Agent": "Mozilla/5.0 (student research; polite, 1 req/s)"}
urls = [
 "https://www.pjm.com/pub/account/lmpda/",
 "https://www.pjm.com/pub/account/lmpda/20221224-da.csv",
 "https://www.pjm.com/pub/account/lmp/",
 "https://www.pjm.com/pub/account/lmp/20221224-rt.csv",
 "https://www.pjm.com/markets-and-operations/energy.aspx",
 "https://dataminer2.pjm.com/feed/da_hrl_lmps",
 "https://dataminer2.pjm.com/feed/da_hrl_lmps/definition",
 "https://api.pjm.com/api/v1/da_hrl_lmps?rowCount=5",
 "https://dataminer2.pjm.com/list",
 "https://dataviewer.pjm.com/dataviewer/pages/public/lmp.jsf",
 "https://www.pjm.com/-/media/markets-ops/energy/lmp-model-info/2022-lmp-hub-average.ashx",
 "https://www.monitoringanalytics.com/reports/PJM_State_of_the_Market/2022.shtml",
 "https://www.monitoringanalytics.com/reports/Reports/2022/2022-som-pjm-sec1.pdf",
 "https://www.pjm.com/markets-and-operations/energy/real-time/monthlylmp.aspx",
 "https://www.pjm.com/markets-and-operations/energy/day-ahead/monthlylmp.aspx",
 "https://www.pjm.com/pub/account/lmpmonthly/",
 "https://www.pjm.com/pub/account/lmpgen/",
]
for u in urls:
    try:
        r = requests.get(u, headers=H, timeout=30)
        ct = r.headers.get("content-type")
        print(r.status_code, len(r.content), ct, u)
        print("   ", r.text[:200].replace("\n", " ") if "text" in (ct or "") or "json" in (ct or "") else "")
        fn = os.path.join(out, u.split("//")[1].replace("/", "_").replace("?", "_")[:100])
        if r.status_code == 200 and len(r.content) < 5_000_000:
            open(fn, "wb").write(r.content)
    except Exception as e:
        print("ERR", u, type(e).__name__, str(e)[:150])
    time.sleep(1.1)
