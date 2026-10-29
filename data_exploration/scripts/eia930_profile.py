import sys; sys.path.append("C:/Users/jltch/AppData/Roaming/Python/Python314/site-packages")
import sys,pandas as pd
d=sys.argv[1]
pd.set_option('display.width',250);pd.set_option('display.max_columns',30)
for f,cal in [('EIA930_BALANCE_2022_Jul_Dec.csv',[('2022-12-21','2022-12-26')]),('EIA930_BALANCE_2025_Jan_Jun.csv',[('2025-01-19','2025-01-24'),('2025-06-22','2025-06-26')])]:
    df=pd.read_csv(d+'/'+f,low_memory=False)
    print('=====',f,df.shape); print(list(df.columns))
    p=df[df['Balancing Authority']=='PJM'].copy()
    print('BAs',df['Balancing Authority'].nunique(),'PJM rows',len(p))
    p['utc']=pd.to_datetime(p['UTC Time at End of Hour'])
    p['lt']=pd.to_datetime(p['Local Time at End of Hour'])
    print('range',p['lt'].min(),p['lt'].max(),'dups',p['utc'].duplicated().sum())
    print('missing share PJM:');print(p.isna().mean()[['Demand Forecast (MW)','Demand (MW)','Demand (MW) (Imputed)','Demand (MW) (Adjusted)','Net Generation (MW)']])
    print(p[['Demand (MW)','Demand Forecast (MW)','Demand (MW) (Adjusted)']].describe())
    print('imputed demand rows',p['Demand (MW) (Imputed)'].notna().sum())
    p['date']=p['lt'].apply(lambda t:(t-pd.Timedelta(hours=1)).normalize())
    for a,b in cal:
        s=p[(p['date']>=a)&(p['date']<=b)]
        g=s.groupby('date').agg(dem_max=('Demand (MW)','max'),adj_max=('Demand (MW) (Adjusted)','max'),fc_max=('Demand Forecast (MW)','max'),n=('Demand (MW)','size'),nmiss=('Demand (MW)',lambda x:x.isna().sum()))
        g['argmax_he']=s.loc[s.groupby('date')['Demand (MW)'].idxmax()].set_index('date')['Hour Number']
        print(g)
    print(p[['Demand (MW)']].sort_values('Demand (MW)').tail(3))
    print(p.nlargest(3,'Demand (MW)')[['Data Date','Hour Number','Demand (MW)','Demand Forecast (MW)']])
    print(p.nsmallest(3,'Demand (MW)')[['Data Date','Hour Number','Demand (MW)']])
    print('fc/dem ratio',(p['Demand Forecast (MW)']/p['Demand (MW)']).describe())
    print('PJM-like BAs:',sorted(b for b in df['Balancing Authority'].unique() if b in('PJM','DOM','AEP','COMED','DUK','NYIS','MISO','TVA')))
    del df
s=pd.read_csv(d+'/EIA930_SUBREGION_2022_Jul_Dec.csv')
pj=s[s['Balancing Authority']=='PJM']
print('SUBREGION BAs',s['Balancing Authority'].unique()); print('PJM subregions',pj['Sub-Region'].unique() if len(pj) else None)
if len(pj):
    pj=pj.copy(); print(pj.groupby('Sub-Region')['Demand (MW)'].agg(['count','max','min']), pj['Demand (MW)'].isna().mean())
    print(pj[pj['Data Date'].isin(['12/23/2022','12/24/2022'])].groupby(['Sub-Region','Data Date'])['Demand (MW)'].max())
