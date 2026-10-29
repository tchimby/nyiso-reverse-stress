import sys, requests, time, os
out=sys.argv[1]
base="http://mis.nyiso.com/public/csv/"
tests=[]
for ym in ["20010101","20100101","20140101","20190101"]:
    tests.append(("damlbmp",f"{ym}damlbmp_zone_csv.zip"))
tests.append(("realtime","20140101realtime_zone_csv.zip"))
tests.append(("realtime","20010101realtime_zone_csv.zip"))
tests.append(("realtime","20190101realtime_zone_csv.zip"))
tests.append(("rtlbmp","20140101rtlbmp_zone_csv.zip"))
for d,f in tests:
    u=f"{base}{d}/{f}"
    try:
        r=requests.head(u,timeout=30,allow_redirects=True)
        print(u,r.status_code,r.headers.get('Content-Length'),r.headers.get('Content-Type'))
    except Exception as e: print(u,"ERR",e)
    time.sleep(1.1)
for u in ["http://mis.nyiso.com/public/","http://mis.nyiso.com/public/P-24Alist.htm","http://mis.nyiso.com/public/P-4Alist.htm"]:
    try:
        r=requests.get(u,timeout=30); print(u,r.status_code,len(r.text))
        open(os.path.join(out,u.rstrip('/').split('/')[-1] or 'index.htm'),'w',encoding='utf8').write(r.text)
    except Exception as e: print(u,"ERR",e)
    time.sleep(1.1)
