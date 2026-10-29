import sys, requests, time, os
out=sys.argv[1]
months=["20240301","20241101"]
for m in months:
    for d,s in [("damlbmp","damlbmp_zone_csv"),("realtime","realtime_zone_csv"),("rtlbmp","rtlbmp_zone_csv")]:
        f=f"{m}{s}.zip"; u=f"http://mis.nyiso.com/public/csv/{d}/{f}"
        p=os.path.join(out,f)
        if os.path.exists(p): continue
        r=requests.get(u,timeout=120); print(u,r.status_code,len(r.content))
        if r.status_code==200: open(p,'wb').write(r.content)
        time.sleep(1.2)
