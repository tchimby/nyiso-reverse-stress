import sys,re,pandas as pd,io
d=sys.argv[1]; h=sys.argv[2]
t=open(d+"/n3050ny3m.htm",encoding="utf8",errors="ignore").read()
rows=[]
for tr in re.findall(r"<tr.*?</tr>",t,re.S):
    c=[re.sub(r"<[^>]+>|&nbsp;"," ",x).strip() for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>",tr,re.S)]
    if len(c)>=12 and re.match(r"^\d{4}$",c[0].strip()): rows.append(c[:13])
    elif c and re.search(r"Year|Jan",c[0]) and len(c)>5: print("HDR",c)
print(len(rows)); 
for r in rows: 
    if r[0] in ("2013","2014","2015","2019","2022","2023","2024","2025","2026"): print(r)
print(t[t.find("Release Date"):t.find("Release Date")+200] if "Release Date" in t else "")
print(re.sub(r"<[^>]+>"," ",t)[-900:])
# HH
hh=pd.read_csv(h); print(hh.columns.tolist()); hh["date"]=pd.to_datetime(hh.iloc[:,0])
col=hh.columns[1]
for a,b in [("2014-01-02","2014-01-10"),("2022-12-19","2022-12-30"),("2025-01-17","2025-01-24"),("2025-06-20","2025-06-27")]:
    print(hh[(hh.date>=a)&(hh.date<=b)][["date",col]].to_string(index=False))
