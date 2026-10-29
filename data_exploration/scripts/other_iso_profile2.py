import sys, csv
sys.path.append(r"C:\Users\jltch\AppData\Roaming\Python\Python314\site-packages")
import pandas as pd
d=sys.argv[1]
for f in ["isone_da_20221223.csv","isone_da_20250122.csv","isone_rt_20221223.csv","isone_probe_20161222.csv"]:
    rows=list(csv.reader(open(d+"/"+f,encoding="utf-8",errors="replace")))
    h=[r for r in rows if r and r[0]=="H"][0][1:]; D=[r[1:len(h)+1] for r in rows if r and r[0]=="D"]
    df=pd.DataFrame(D,columns=h); print("ISONE",f,df.shape,h[:8])
    lp=[c for c in h if "Locational Marginal" in c][0]; df[lp]=pd.to_numeric(df[lp])
    hub=df[df["Location Name"].str.contains("HUB",case=False)]
    print(hub.groupby("Location Name")[lp].agg(["count","mean","max","min"]).to_string())
    print("null share",df.isna().mean().max())
for f in ["miso_da_20250122.csv","miso_rt_20250122.csv","miso_probe_20231223.csv"]:
    df=pd.read_csv(d+"/"+f,skiprows=lambda i:i in(0,1,2,3),nrows=None)
    print("MISO",f,df.shape,list(df.columns)[:6])
    hb=df[(df.Node.str.contains("HUB",na=False))&(df.Value=="LMP")]
    print(hb.iloc[:,[0,1,2]+list(range(3,27))].assign(mean=hb.iloc[:,3:27].mean(axis=1),mx=hb.iloc[:,3:27].max(axis=1))[["Node","mean","mx"]].head(6).to_string())
    print("null share",df.isna().mean().max().round(3))
