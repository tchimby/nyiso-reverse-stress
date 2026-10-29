import sys, zipfile, io, pandas as pd
d=sys.argv[1]
for m in ["20140101","20221201","20250101"]:
    for s in ["damlbmp_zone_csv","realtime_zone_csv","rtlbmp_zone_csv"]:
        z=zipfile.ZipFile(f"{d}/{m}{s}.zip"); n=z.namelist()
        print(m,s,len(n),n[:2],n[-1])
z=zipfile.ZipFile(f"{d}/20250101realtime_zone_csv.zip")
for f in z.namelist()[:1]:
    print(z.read(f).decode()[:600])
z=zipfile.ZipFile(f"{d}/20250101damlbmp_zone_csv.zip")
print(z.read(z.namelist()[0]).decode()[:500])
z=zipfile.ZipFile(f"{d}/20250101rtlbmp_zone_csv.zip")
print(z.read(z.namelist()[0]).decode()[:500])
