import sys, pandas as pd
pd.set_option("display.width",250)
d=sys.argv[1]
c=pd.read_excel(d+"/ice_electric-2026.xlsx"); c.columns=[str(x).replace("\n","").strip() for x in c.columns]
w=c[c["Price hub"]=="PJM WH Real Time Peak"].copy()
w["Trade date"]=pd.to_datetime(w["Trade date"])
print(w[w["Wtd avg price $/MWh"]>150][["Trade date","Delivery start date","High price $/MWh","Low price $/MWh","Wtd avg price $/MWh","Daily volume MWh","Number of trades"]].to_string())
print(w[(w["Trade date"]>="2026-01-15")&(w["Trade date"]<="2026-02-10")][["Trade date","Wtd avg price $/MWh","Daily volume MWh"]].to_string())
for f in ["ice_electric-2022final.xlsx","ice_electric-2025final.xlsx","ice_electric-2026.xlsx"]:
    df=pd.read_excel(d+"/"+f)
    n=sum(isinstance(v,str) for col in df.columns[4:] for v in df[col])
    print(f,"string cells in numeric cols",n)
