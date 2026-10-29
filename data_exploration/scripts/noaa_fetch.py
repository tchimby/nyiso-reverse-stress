import sys, time, os, requests
out = sys.argv[1]
stations = {
 "PHL": "USW00013739", "PIT": "USW00094823", "DCA": "USW00013743",
 "ORD": "USW00094846", "CMH": "USW00014821", "CLE": "USW00014820"}
for k, v in stations.items():
    url = f"https://www.ncei.noaa.gov/data/daily-summaries/access/{v}.csv"
    try:
        r = requests.get(url, timeout=120)
        print(k, v, r.status_code, len(r.content))
        if r.status_code == 200:
            open(os.path.join(out, f"{k}_{v}.csv"), "wb").write(r.content)
    except Exception as e:
        print(k, v, "ERR", e)
    time.sleep(1.5)
