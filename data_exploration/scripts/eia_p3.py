import sys, pandas as pd
pd.set_option("display.width",250)
d=sys.argv[1]
def load(f):
    x=pd.ExcelFile(d+"/"+f); df=x.parse(x.sheet_names[0]); df.columns=[str(c).replace("\n","").strip() for c in df.columns]
    for c in ["Trade date","Delivery start date","Delivery end date"]: df[c]=pd.to_datetime(df[c])
    return df
a=load("ice_electric-2022final.xlsx"); b=load("ice_electric-2025final.xlsx"); c=load("ice_electric-2026.xlsx")
cols=["Price hub","Trade date","Delivery start date","Delivery end date","High price $/MWh","Low price $/MWh","Wtd avg price $/MWh","Daily volume MWh","Number of trades"]
w=a[a["Price hub"]=="PJM WH Real Time Peak"]
print(w[(w["Trade date"]>="2022-12-14")&(w["Trade date"]<="2022-12-30")][cols].drop(columns="Price hub").to_string())
w=b[b["Price hub"]=="PJM WH Real Time Peak"]
print(w[(w["Trade date"]>="2025-01-13")&(w["Trade date"]<="2025-01-31")][cols].drop(columns="Price hub").to_string())
print(w[(w["Trade date"]>="2025-06-18")&(w["Trade date"]<="2025-06-30")][cols].drop(columns="Price hub").to_string())
for n,df in [("2022",a),("2025",b),("2026",c)]:
    w=df[df["Price hub"]=="PJM WH Real Time Peak"]
    print(n,"WH rows",len(w),"price describe"); print(w["Wtd avg price $/MWh"].describe().round(2).to_string())
    print("missing wtd share",w["Wtd avg price $/MWh"].isna().mean(),"delivery span days mean",((w["Delivery end date"]-w["Delivery start date"]).dt.days).value_counts().to_dict())
    print("unique hubs raw", df["Price hub"].unique().tolist())
    print("duplicate trade date rows", w["Trade date"].duplicated().sum())
