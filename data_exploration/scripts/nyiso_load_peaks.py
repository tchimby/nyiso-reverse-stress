import sys, zipfile, io, pandas as pd
d=sys.argv[1]
def rd(m,f):
    z=zipfile.ZipFile(f"{d}/{m}{f}_csv.zip"); out=[]
    for n in z.namelist():
        out.append(pd.read_csv(io.BytesIO(z.read(n)),encoding='latin1'))
    return pd.concat(out)
res=[]
for m in ['20140101','20221201','20250101','20250601']:
    pi=rd(m,'palIntegrated'); pi['t']=pd.to_datetime(pi['Time Stamp'])
    nz=pi.groupby('Time Stamp')['Name'].nunique(); print(m,'zones/ts min/max',nz.min(),nz.max(),'ts',len(nz))
    h=pi.groupby('t')['Integrated Load'].sum()
    p=rd(m,'pal'); p['t']=pd.to_datetime(p['Time Stamp'])
    f5=p.groupby('t')['Load'].sum()
    lf=rd(m,'isolf'); lf['t']=pd.to_datetime(lf['Time Stamp'])
    print(' isolf rows',len(lf),'dups ts',lf['t'].duplicated().sum(), 'rows/day', len(lf)/ (len(set(lf.t.dt.date))))
    lf=lf.drop_duplicates('t',keep='last').set_index('t')['NYISO']
    for day in sorted(set(h.index.date)):
        hh=h[h.index.date==day]; ff=f5[f5.index.date==day]; ll=lf[lf.index.date==day]
        ph=hh.idxmax(); pf=ff.idxmax()
        res.append(dict(date=day,peak_int=hh.max(),peak_int_hr=ph.hour,peak_5min=ff.max(),peak_5min_t=pf.strftime('%H:%M'),fc_peak=ll.max() if len(ll) else None,fc_peak_hr=ll.idxmax().hour if len(ll) else None,fc_at_actual_peak_hr=lf.get(ph),n_h=len(hh),n_fc=len(ll)))
r=pd.DataFrame(res); r['err_MW']=r.fc_at_actual_peak_hr-r.peak_int; r['err_pct']=100*r.err_MW/r.peak_int
r['pkerr_MW']=r.fc_peak-r.peak_int
pd.set_option('display.width',250); pd.set_option('display.max_rows',500)
r.to_csv(sys.argv[2],index=False)
print(r.sort_values('peak_int',ascending=False).groupby(r.date.astype(str).str[:7]).head(4).round(1).to_string())
print(r.groupby(r.date.astype(str).str[:7])[['err_MW','err_pct','pkerr_MW']].agg(['mean','min','max']).round(2))
