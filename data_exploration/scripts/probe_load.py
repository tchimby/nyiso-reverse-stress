import sys, time, requests
out=sys.argv[1]
urls=["https://www.pjm.com/markets-and-operations/energy.aspx",
"https://www.pjm.com/pub/operations/hist-meter-load/2022-hourly-loads.xls",
"https://www.pjm.com/pub/operations/hist-meter-load/2022-hourly-loads.csv",
"https://www.pjm.com/pub/operations/hist-meter-load/",
"https://www.pjm.com/markets-and-operations/ops-analysis/historical-load-data",
"https://www.pjm.com/library/data-miner",
"https://dataminer2.pjm.com/feed/hrl_load_metered/definition",
"https://dataminer2.pjm.com/feed/load_frcstd_hist/definition",
"https://www.monitoringanalytics.com/reports/Reports/2023/IMM_2022_State_of_the_Market_Report_for_PJM_Volume_2.pdf"]
H={"User-Agent":"Mozilla/5.0 (student research)"}
for u in urls:
    try:
        r=requests.get(u,headers=H,timeout=30,stream=True)
        c=next(r.iter_content(2000),b"")
        print(r.status_code,u,r.headers.get("content-type"),r.headers.get("content-length"),c[:150])
    except Exception as e: print("ERR",u,repr(e)[:150])
    time.sleep(1.2)
