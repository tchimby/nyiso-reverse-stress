import sys, pandas as pd
d=sys.argv[1]
try:
    import xlrd; print("xlrd",xlrd.__version__)
except Exception as e: print("no xlrd",e)
for f in ["ice_electric-2022final.xlsx"]:
    try:
        x=pd.ExcelFile(d+"/"+f); print(f,x.sheet_names)
        for s in x.sheet_names:
            df=x.parse(s,header=None,nrows=5); print(s,df.shape); print(df.to_string()[:900])
    except Exception as e: print(f,"ERR",e)
