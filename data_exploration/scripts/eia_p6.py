import sys, pandas as pd
pd.set_option("display.width",250)
sys.path.insert(0, sys.argv[2])
from xls_min import read_xls
sh,c=read_xls(sys.argv[1]+"/ice_electric-2014final.xls")
cells=c[0]; R=max(r for r,_ in cells); C=max(cc for _,cc in cells)
rows=[[cells.get((r,cc)) for cc in range(C+1)] for r in range(R+1)]
df=pd.DataFrame(rows[1:],columns=[str(x).replace("\n","") for x in rows[0]])
for cc in ["Trade date","Delivery start date","Delivery end date"]:
    df[cc]=pd.to_datetime(df[cc],unit="D",origin="1899-12-30",errors="coerce")
print(df.shape); print(df.head(3).to_string())
g=df.groupby("Price hub").agg(n=("Trade date","size"),t0=("Trade date","min"),t1=("Trade date","max")); print(g.to_string())
print("hub null share",df["Price hub"].isna().mean(), "wtd null",df["Wtd avg price $/MWh"].isna().mean())
w=df[df["Price hub"].astype(str).str.contains("PJM")]
print(w[(w["Trade date"]>="2014-01-02")&(w["Trade date"]<="2014-02-05")].drop(columns=["Delivery end date","Change"]).to_string())
print("hubs with PJM/Dom/Indiana/Nepool:",[h for h in g.index if any(k in str(h) for k in ["PJM","Dom","Indiana","Nepool","NI","AEP"])])
