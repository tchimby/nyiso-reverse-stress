import sys, zipfile, io, pandas as pd
d=sys.argv[1]; peaks=pd.read_csv(sys.argv[2],parse_dates=['date'])
rows=[]
for m in ['20140101','20221201','20250101','20250601']:
    z=zipfile.ZipFile(f"{d}/{m}isolf_csv.zip"); fc={}
    for n in z.namelist():
        iss=pd.Timestamp(n[:8]); df=pd.read_csv(io.BytesIO(z.read(n))); df['t']=pd.to_datetime(df['Time Stamp'])
        fc[iss]=df.set_index('t')['NYISO']
    pk=peaks[peaks.date.dt.strftime('%Y%m')==m[:6]]
    for _,r in pk.iterrows():
        D=r.date; ph=pd.Timestamp(D)+pd.Timedelta(hours=int(r.peak_int_hr))
        for lag,name in [(1,'da'),(0,'sameday')]:
            s=fc.get(D-pd.Timedelta(days=lag))
            if s is None: continue
            sd=s[s.index.normalize()==D]
            r_=dict(date=D,vint=name,fc_at_peakhr=s.get(ph),fc_dayMax=sd.max(),act_peak=r.peak_int,act_hr=r.peak_int_hr)
            rows.append(r_)
x=pd.DataFrame(rows); x['err_at_hr']=x.fc_at_peakhr-x.act_peak; x['pct']=100*x.err_at_hr/x.act_peak; x['maxerr']=x.fc_dayMax-x.act_peak; x['maxpct']=100*x.maxerr/x.act_peak
x.to_csv(sys.argv[3],index=False)
pd.set_option('display.width',250)
x['mo']=x.date.dt.strftime('%Y-%m')
print(x.groupby(['mo','vint'])[['pct','maxpct']].agg(['mean','min','max']).round(2))
for dd in ['2014-01-07','2014-01-06','2022-12-23','2022-12-24','2025-01-22','2025-01-21','2025-06-24','2025-06-23','2025-06-25']:
    print(x[x.date==dd].drop(columns='mo').round(1).to_string(header=False))
