import sys, zipfile, io
sys.path.append(r"C:\Users\jltch\AppData\Roaming\Python\Python314\site-packages")
import pandas as pd
d = sys.argv[1]
def zr(z, name):
    return pd.read_csv(io.BytesIO(zipfile.ZipFile(d+"/"+z).read(name)))
# NYISO
for z in ["nyiso_damlbmp_20221201damlbmp_zone_csv.zip","nyiso_damlbmp_20250101damlbmp_zone_csv.zip","nyiso_damlbmp_20140101damlbmp_zone_csv.zip","nyiso_realtime_20221201realtime_zone_csv.zip"]:
    zf=zipfile.ZipFile(d+"/"+z); names=zf.namelist()
    print("NYISO",z,len(names),names[0],names[-1])
    day = [n for n in names if n.startswith(("20221223","20250122","20140107"))][0]
    df=pd.read_csv(io.BytesIO(zf.read(day))); print(day, df.shape, list(df.columns)); 
    print(df.groupby("Name").iloc[:,0].size().head(2) if False else df["Name"].nunique(),"zones; nulls",df.isna().mean().round(3).to_dict())
    c=[x for x in df.columns if "LBMP" in x][0]
    s=df[df.Name.isin(["WEST","N.Y.C.","CAPITL"])].groupby("Name")[c].agg(["mean","max","min","count"]); print(s)
# CAISO
for f in ["caiso_dam_20250122.zip"]:
    zf=zipfile.ZipFile(d+"/"+f); df=pd.read_csv(io.BytesIO(zf.read(zf.namelist()[0])))
    print("CAISO",df.shape,list(df.columns)); 
    p=df[df.LMP_TYPE=="LMP"]; print(p.groupby("NODE")["MW"].agg(["count","mean","max","min"]))
# ISO-NE
for f in ["isone_da_20221223.csv","isone_da_20250122.csv","isone_rt_20221223.csv"]:
    df=pd.read_csv(d+"/"+f,skiprows=4); df=df[df.iloc[:,0]=="D"]
    df.columns=pd.read_csv(d+"/"+f,skiprows=4,nrows=0).columns if False else df.columns
    print("ISONE",f,df.shape)
