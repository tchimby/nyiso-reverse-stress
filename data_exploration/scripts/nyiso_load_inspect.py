import sys, zipfile, io, pandas as pd
d=sys.argv[1]
for m in ['20140101','20221201','20250101','20250601']:
    for f in ['palIntegrated','pal','isolf']:
        z=zipfile.ZipFile(f"{d}/{m}{f}_csv.zip"); n=z.namelist()
        raw=z.read(n[0]).decode('latin1').splitlines()
        print(m,f,len(n),n[0],n[-1]); print('  ',raw[:3]); 
        if m=='20140101':
            df=pd.read_csv(io.StringIO("\n".join(raw)));print('  cols',list(df.columns)); print('  uniq names',df.iloc[:,2].unique()[:20] if df.shape[1]>2 else '')
