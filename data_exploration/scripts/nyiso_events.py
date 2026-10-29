import sys, zipfile, io, pandas as pd, numpy as np, glob, os
d=sys.argv[1]
def load(suf,usecols=6):
    fr=[]
    for p in sorted(glob.glob(f"{d}/*{suf}.zip")):
        z=zipfile.ZipFile(p)
        for n in z.namelist():
            df=pd.read_csv(io.BytesIO(z.read(n)),usecols=range(7) if suf.startswith('rtlbmp') and '2014' in p else range(6))
            c=list(df.columns); df=df.rename(columns=dict(zip(c[:6],['ts','name','ptid','lbmp','loss','cong'])))
            fr.append(df)
    df=pd.concat(fr,ignore_index=True)
    df['t']=pd.to_datetime(df.ts,format='mixed'); return df
da=load('damlbmp_zone_csv'); hr=load('rtlbmp_zone_csv'); rt=load('realtime_zone_csv')
for df in (da,hr): df['hb']=df.t.dt.hour; df['day']=df.t.dt.normalize()
# rt: interval ending; assign to hour-beginning via t-1s
rt['tt']=rt.t-pd.Timedelta(seconds=1); rt['hb']=rt.tt.dt.hour; rt['day']=rt.tt.dt.normalize()
rt['ongrid']=(rt.t.dt.second==0)&(rt.t.dt.minute%5==0)
for df in (da,hr,rt):
    df['wd']=df.day.dt.dayofweek<5
    df['on']=df.wd&df.hb.between(7,22)
def daily(df,col,z):
    s=df[df.name==z]
    g=s.groupby(['day','on'])[col].mean().unstack()
    g.columns=['off' if c is False else 'on' for c in g.columns]
    return g
rows={}
for z in ['WEST','N.Y.C.']:
    for nm,df in [('DA',da),('RTh',hr)]:
        g=daily(df,'lbmp',z)
        rows[(z,nm,'on')]=g['on']; rows[(z,nm,'off')]=g['off']
    g=daily(rt[rt.ongrid],'lbmp',z); rows[(z,'RT5','on')]=g['on']; rows[(z,'RT5','off')]=g['off']
D=pd.DataFrame(rows)
D.to_csv(os.path.join(sys.argv[2],'nyiso_daily_onoff.csv'))
pd.set_option('display.width',250); pd.set_option('display.max_columns',30)
ev={'2014-01-06':'','2014-01-07':'','2014-01-08':'','2022-12-22':'','2022-12-23':'','2022-12-24':'','2022-12-25':'','2025-01-20':'','2025-01-21':'','2025-01-22':'','2025-01-23':'','2025-06-23':'','2025-06-24':'','2025-06-25':'','2025-06-26':''}
E=D.loc[[pd.Timestamp(k) for k in ev]].round(1)
E.columns=['_'.join(c) for c in E.columns]
print(E.T.to_string())
# spread & gap
for k in ev:
    t=pd.Timestamp(k)
    print(k,'NYC-WEST on DA %.1f RTh %.1f | DA-RTh gap on WEST %.1f NYC %.1f | off WEST %.1f NYC %.1f'%(D.loc[t,('N.Y.C.','DA','on')]-D.loc[t,('WEST','DA','on')],D.loc[t,('N.Y.C.','RTh','on')]-D.loc[t,('WEST','RTh','on')],D.loc[t,('WEST','DA','on')]-D.loc[t,('WEST','RTh','on')],D.loc[t,('N.Y.C.','DA','on')]-D.loc[t,('N.Y.C.','RTh','on')],D.loc[t,('WEST','DA','off')]-D.loc[t,('WEST','RTh','off')],D.loc[t,('N.Y.C.','DA','off')]-D.loc[t,('N.Y.C.','RTh','off')]))
# max in windows
wins={'2014-01-06..08':('2014-01-06','2014-01-08'),'2022-12-22..25':('2022-12-22','2022-12-25'),'2025-01-20..23':('2025-01-20','2025-01-23'),'2025-06-23..26':('2025-06-23','2025-06-26')}
for k,(a,b) in wins.items():
    a=pd.Timestamp(a);b=pd.Timestamp(b)
    for nm,df in [('DA',da),('RTh',hr),('RT5all',rt)]:
        s=df[(df.day>=a)&(df.day<=b)]
        i=s.lbmp.idxmax(); j=s.lbmp.idxmin()
        print(k,nm,'max',s.loc[i,['t','name','lbmp','loss','cong']].tolist(),'min',s.loc[j,['t','name','lbmp']].tolist())
        for z in ['WEST','N.Y.C.']:
            q=s[s.name==z]; i=q.lbmp.idxmax()
            print('   ',z,'max',q.loc[i,'t'],q.loc[i,'lbmp'],'cong',q.loc[i,'cong'])
# overall extremes by month
for nm,df in [('DA',da),('RTh',hr),('RT5',rt)]:
    print(nm,'overall max',df.lbmp.max(),'min',df.lbmp.min())
    print(df.groupby(df.t.dt.to_period('M')).lbmp.agg(['max','min']).T.round(1).to_string())
    print((df.lbmp>=900).sum(),'rows >=900;', (df.lbmp>=1000).sum(),'>=1000')
print(hr.columns.tolist())
