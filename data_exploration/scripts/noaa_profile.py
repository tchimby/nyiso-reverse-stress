import sys, glob, os
import pandas as pd, numpy as np
d = sys.argv[1]
frames = {}
for f in sorted(glob.glob(os.path.join(d, "*.csv"))):
    k = os.path.basename(f).split("_")[0]
    df = pd.read_csv(f, low_memory=False)
    df["DATE"] = pd.to_datetime(df["DATE"])
    print(k, "rows", len(df), "range", df.DATE.min().date(), df.DATE.max().date(), "cols", list(df.columns)[:12])
    s = df[df.DATE >= "2014-01-01"].set_index("DATE")
    full = pd.date_range("2014-01-01", s.index.max())
    print("  2014+ expected days", len(full), "present", len(s))
    for c in ["TMAX", "TMIN", "TAVG"]:
        if c in s:
            print(f"  {c}: nonnull {s[c].notna().sum()} missing share vs expected {1 - s[c].notna().sum()/len(full):.4f}")
        else: print("  ", c, "absent")
    # check units: values in tenths C or F?
    print("  TMAX sample", s["TMAX"].dropna().head(3).tolist())
    frames[k] = s.reindex(full)
    frames[k].index.name = "DATE"
def conv(x): return x  # daily-summaries units=standard => F? checked below
tmax = pd.DataFrame({k: v["TMAX"] for k, v in frames.items()})/10*1.8+32
tmin = pd.DataFrame({k: v["TMIN"] for k, v in frames.items()})/10*1.8+32
print("TMAX overall mean by station", tmax.mean().round(1).to_dict())
tavg = (tmax + tmin) / 2
hdd = (65 - tavg).clip(lower=0); cdd = (tavg - 65).clip(lower=0)
wins = {"Elliott": ("2022-12-20", "2022-12-26"), "Jan2025": ("2025-01-18", "2025-01-24"), "Jun2025": ("2025-06-20", "2025-06-26"), "Jan2014": ("2014-01-04", "2014-01-08")}
for n, (a, b) in wins.items():
    print("==", n)
    print("TAVG (tmax+tmin)/2:"); print(tavg.loc[a:b].round(1).assign(mean=tavg.loc[a:b].mean(axis=1).round(1)))
    print("HDD mean:"); print(hdd.loc[a:b].mean(axis=1).round(1).to_dict() if False else hdd.loc[a:b].mean(axis=1).round(1).to_string())
    print("CDD mean:"); print(cdd.loc[a:b].mean(axis=1).round(1).to_string())
# missing in multi-station mean
n = tavg.notna().sum(axis=1)
print("days with all 6 stations:", (n == 6).sum(), "of", len(n), " >=4:", (n >= 4).sum(), " zero:", (n == 0).sum())
print("latest date with data:", tavg.dropna(how="all").index.max())
