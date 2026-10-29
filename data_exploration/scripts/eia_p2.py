import sys, pandas as pd
d=sys.argv[1]
for f in ["ice_electric-2022final.xlsx","ice_electric-2025final.xlsx","ice_electric-2026.xlsx"]:
    x=pd.ExcelFile(d+"/"+f); print("=====",f,x.sheet_names)
    df=x.parse(x.sheet_names[0]); df.columns=[str(c).replace("\n","").strip() for c in df.columns]
    raw=df["Trade date"]; df["td"]=pd.to_datetime(raw,errors="coerce")
    bad=df[df.td.isna()]; print("rows",len(df),"unparsed trade dates",len(bad)); print(bad.head(3).to_string()[:500])
    df["ds"]=pd.to_datetime(df["Delivery start date"],errors="coerce")
    print(df.groupby("Price hub").agg(n=("td","size"),t0=("td","min"),t1=("td","max")).to_string())
