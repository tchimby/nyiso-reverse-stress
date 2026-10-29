import sys, re, datetime as dt, pandas as pd
pd.set_option("display.width",250)
d=sys.argv[1]
M={m:i+1 for i,m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}
t=open(d+"/rngwhhdD.htm",encoding="latin1").read()
rows=[]; bad=0; nonmon=0
for tr in re.findall(r"<tr[^>]*>(.*?)</tr>",t,flags=re.S):
    m=re.search(r"(\d{4}) (\w{3})-\s*(\d+) to (\w{3})-\s*(\d+)",tr)
    if not m: continue
    y,mo,da=int(m.group(1)),M[m.group(2)],int(m.group(3))
    start=dt.date(y,mo,da)
    if start.weekday()!=0: nonmon+=1
    cells=re.findall(r"<td class='B3'>(.*?)</td>",tr)
    for i,c in enumerate(cells):
        dd=start+dt.timedelta(days=i)
        v=c.replace("&nbsp;","").strip()
        rows.append((dd,float(v) if re.fullmatch(r"-?[0-9.]+",v) else None))
hh=pd.DataFrame(rows,columns=["date","hh_usd"]); hh["date"]=pd.to_datetime(hh.date)
print("HH rows(weekday slots)",len(hh),"non-Monday week starts",nonmon,"range",hh.date.min().date(),hh.date.max().date())
print("missing share overall",round(hh.hh_usd.isna().mean(),4))
h=hh[hh.date>="2014-01-01"]; print("since 2014 slots",len(h),"missing share",round(h.hh_usd.isna().mean(),4)); h=hh[hh.date>="2019-01-01"]; print("since 2019 slots",len(h),"missing",h.hh_usd.isna().sum(),round(h.hh_usd.isna().mean(),4))
print("last obs", hh.dropna().tail(3).to_string())
print("min/max since2014",hh[hh.date>="2014-01-01"].hh_usd.agg(["min","max"]).tolist())
for a,b in [("2014-01-02","2014-01-10"),("2022-12-19","2022-12-30"),("2025-01-15","2025-01-27"),("2025-06-18","2025-06-27"),("2026-01-20","2026-02-03")]:
    print(a,b); print(hh[(hh.date>=a)&(hh.date<=b)].set_index("date").hh_usd.to_dict())
hh[hh.date>="2013-12-01"].to_csv(d+"/hh_daily_2013-12_onward_parsed.csv",index=False,date_format="%Y-%m-%d")
print("idxmax since 2019:",hh[hh.date>="2019-01-01"].sort_values("hh_usd").tail(3).to_string())
# citygate
allc=[]
for s in ["us","pa","nj","md","oh","va"]:
    t=open(d+f"/n3050{s}3m.htm",encoding="latin1").read()
    ttl=re.search(r"<title>(.*?)</title>",t,flags=re.S).group(1).strip()
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>",t,flags=re.S):
        m=re.search(r"<td class='B4'>&nbsp;&nbsp;(\d{4})</td>",tr)
        if not m: continue
        cells=re.findall(r"<td class='B3'>(.*?)</td>",tr)
        for i,c in enumerate(cells):
            v=c.replace("&nbsp;","").strip()
            allc.append((s.upper(),pd.Timestamp(int(m.group(1)),i+1,1),float(v) if re.fullmatch(r"-?[0-9.]+",v) else None))
    print(s,ttl)
cg=pd.DataFrame(allc,columns=["st","month","usd_mcf"])
for s,g in cg.groupby("st"):
    gg=g.dropna(); print(s,"months",len(g),"nonnull",len(gg),gg.month.min().date(),gg.month.max().date(),"missing since2019",g[g.month>="2019-01-01"].usd_mcf.isna().sum())
p=cg.pivot(index="month",columns="st",values="usd_mcf")
print(p.loc[["2022-11-01","2022-12-01","2023-01-01","2024-12-01","2025-01-01","2025-02-01","2025-06-01","2026-01-01","2026-07-01","2026-08-01"]].to_string())
p[p.index>="2013-12-01"].to_csv(d+"/citygate_monthly_2013-12_onward_parsed.csv",date_format="%Y-%m-%d")
# monthly HH avg vs PA citygate
hm=hh.dropna().set_index("date").hh_usd.resample("MS").mean()
j=pd.concat([hm.rename("hh_avg"),p],axis=1).dropna()
j=j[j.index>="2019-01-01"]
print("corr levels",j.corr().hh_avg.round(3).to_dict()); print("mean citygate-minus-HH/1.037 spread",(j[["PA","NJ","MD","OH","VA","US"]].sub(j.hh_avg/1.0,axis=0)).mean().round(2).to_dict())
