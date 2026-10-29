import sys, pandas as pd
pd.set_option("display.width",250)
src,scr,out=sys.argv[1:4]
sys.path.insert(0,scr)
from xls_min import read_xls
fr=[]
for y in (2014,2015,2016):
    sh,c=read_xls(f"{src}/ice_natgas-{y}final.xls"); cells=c[0]
    R=max(r for r,_ in cells); C=max(cc for _,cc in cells)
    rows=[[cells.get((r,cc)) for cc in range(C+1)] for r in range(R+1)]
    df=pd.DataFrame(rows[1:],columns=[str(x).replace("\n","").strip() for x in rows[0]])
    for cc in ["Trade date","Delivery start date"]: df[cc]=pd.to_datetime(df[cc],unit="D",origin="1899-12-30",errors="coerce")
    fr.append(df)
d=pd.read_excel(f"{src}/ice_natgas-2017final.xlsx"); d.columns=[str(x).replace("\n","").strip() for x in d.columns]; fr.append(d)
a=pd.concat(fr,ignore_index=True)
a["hub"]=a["Price hub"].astype(str).str.strip()
print(a.groupby("hub").agg(n=("Trade date","size"),t0=("Trade date","min"),t1=("Trade date","max")).to_string())
p=a.pivot_table(index="Delivery start date",columns="hub",values="Wtd avg price $/MMBtu",aggfunc="last")
p.to_csv(out+"/ice_natgas_2014-2017_wtdavg_by_delivery_date.csv")
print(p.describe().T[["count","mean","max"]])
print((p["TETCO-M3"]-p["Henry"]).describe(), (p["Algonquin Citygates"]-p["Henry"]).describe())
print("top Algonquin days:"); print(p.sort_values("Algonquin Citygates",ascending=False).head(8)[["Algonquin Citygates","TETCO-M3","Henry"]])
print("top M3 days:"); print(p.sort_values("TETCO-M3",ascending=False).head(5)[["Algonquin Citygates","TETCO-M3","Henry"]])
