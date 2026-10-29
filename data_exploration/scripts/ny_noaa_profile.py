import sys,glob,os,pandas as pd
pd.set_option("display.width",250)
d=sys.argv[1]
ev=["2014-01-07","2022-12-23","2022-12-24","2025-01-21","2025-01-22","2025-06-24"]
out=[]; cov=[]
for f in sorted(glob.glob(d+"/*.csv")):
    k=os.path.basename(f).split("_USW")[0]
    x=pd.read_csv(f,usecols=lambda c:c in("STATION","DATE","TMAX","TMIN","TAVG","PRCP","SNOW","AWND"),low_memory=False)
    x["DATE"]=pd.to_datetime(x.DATE); x=x.set_index("DATE").sort_index()
    # check units: values appear in degrees F if > 60 in summer
    x["TMAXF"]=x.TMAX/10*9/5+32; x["TMINF"]=x.TMIN/10*9/5+32  # GHCN metric: tenths of degC
    x["tm"]=(x.TMAXF+x.TMINF)/2
    x["HDD"]=(65-x.tm).clip(lower=0); x["CDD"]=(x.tm-65).clip(lower=0)
    for per,(a,b) in {"2014-26":("2014-01-01","2026-10-24"),"2019-26":("2019-01-01","2026-10-24")}.items():
        s=x[a:b]; n=pd.date_range(a,min(pd.Timestamp(b),x.index.max())).size
        cov.append((k,per,x.index.min().date(),x.index.max().date(),len(s),n,int(s.TMAXF.isna().sum()+0),int(s.TMINF.isna().sum()),int(s.tm.isna().sum()), round(100*s.tm.notna().sum()/n,2)))
    for e in ev:
        t=pd.Timestamp(e)
        if t in x.index: r=x.loc[t]; out.append((k,e,round(r.TMAXF,1),round(r.TMINF,1),round(r.tm,1) if pd.notna(r.tm) else None,round(r.HDD,1) if pd.notna(r.HDD) else None,round(r.CDD,1) if pd.notna(r.CDD) else None,r.get("PRCP")/10,r.get("SNOW")))
        else: out.append((k,e,"no row"))
print(pd.DataFrame(cov,columns="stn per first last rows expected tmax_na tmin_na tavg_na pct_ok".split()).to_string(index=False))
o=pd.DataFrame(out,columns="stn date TMAX_F TMIN_F TAVG_F HDD CDD PRCP_mm SNOW_mm".split()); print(o.to_string(index=False))
o.to_csv(sys.argv[2],index=False)
# multi-station mean (NYC trio) event HDD/CDD
