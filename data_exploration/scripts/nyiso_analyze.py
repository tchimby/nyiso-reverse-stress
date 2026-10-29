import sys, zipfile, io, pandas as pd, numpy as np, re
d=sys.argv[1]
months=["20140101","20221201","20250101","20250601","20240401"]
def load(prod,suf):
    fr=[]
    for m in months:
        z=zipfile.ZipFile(f"{d}/{m}{suf}.zip")
        for n in z.namelist():
            df=pd.read_csv(io.BytesIO(z.read(n)),usecols=range(6))
            df.columns=['ts','name','ptid','lbmp','loss','cong']
            df['file']=n; fr.append(df)
    df=pd.concat(fr); df['ts']=pd.to_datetime(df['ts'],format='%m/%d/%Y %H:%M:%S' if prod=='rt' else None, errors='coerce') if prod=='rt' else pd.to_datetime(df['ts'],format='%m/%d/%Y %H:%M')
    return df
da=load('da','damlbmp_zone_csv'); rt=load('rt','realtime_zone_csv'); hr=load('hr','rtlbmp_zone_csv')
for n,df in [('da',da),('rt',rt),('hr',hr)]:
    print(n,len(df),df.ts.isna().sum(),sorted(df.name.unique()), df.ptid.nunique())
    print(df.groupby(df.file.str[:8]).ts.apply(lambda s:s.dt.year.nunique()).max())
# rows per zone per day rt
rt['day']=rt.ts.dt.normalize()
c=rt[rt.name=='WEST'].groupby('day').size()
print('RT WEST rows/day dist',c.value_counts().to_dict())
print(c[c!=288])
# duplicate intervals
dd=rt[rt.name=='WEST'].duplicated('ts',keep=False)
print('RT WEST dup ts',dd.sum())
print(rt[rt.name=='WEST'][dd].head(12))
for n,df in [('da',da),('hr',hr)]:
    df['day']=df.ts.dt.normalize()
    c=df[df.name=='WEST'].groupby('day').size(); print(n,'rows/day',c.value_counts().to_dict()); print(c[c!=24])
# are 'file' day and ts day consistent
print(rt[(rt.ts.dt.strftime('%Y%m%d')!=rt.file.str[:8])].groupby('file').size().head())
# sample seen of 344 rows: other dates?
