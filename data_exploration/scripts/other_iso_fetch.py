import sys, time, os, urllib.request, urllib.error
out = sys.argv[1]
H = {"User-Agent": "Mozilla/5.0 (academic research, low volume)"}
T = [
 ("nyiso_da_20221223","http://mis.nyiso.com/public/csv/damlbmp/20221223damlbmp_zone.csv"),
 ("nyiso_rt_20221223","http://mis.nyiso.com/public/csv/realtime/20221223realtime_zone.csv"),
 ("nyiso_da_20250122","http://mis.nyiso.com/public/csv/damlbmp/20250122damlbmp_zone.csv"),
 ("nyiso_da_20140107","http://mis.nyiso.com/public/csv/damlbmp/20140107damlbmp_zone.csv"),
 ("caiso_dam_20221223","https://oasis.caiso.com/oasisapi/SingleZip?queryname=PRC_LMP&startdatetime=20221223T08:00-0000&enddatetime=20221224T08:00-0000&version=1&market_run_id=DAM&node=TH_NP15_GEN-APND&resultformat=6"),
 ("caiso_dam_20250122","https://oasis.caiso.com/oasisapi/SingleZip?queryname=PRC_LMP&startdatetime=20250122T08:00-0000&enddatetime=20250123T08:00-0000&version=1&market_run_id=DAM&node=TH_NP15_GEN-APND&resultformat=6"),
 ("isone_da_20221223","https://www.iso-ne.com/transform/csv/hourlylmp/da?start=20221223&end=20221223"),
 ("isone_static_da","https://www.iso-ne.com/static-assets/documents/markets/historical/2022_smd_hourly.xlsx"),
 ("miso_da_20221223","https://docs.misoenergy.org/marketreports/20221223_da_expost_lmp.csv"),
 ("miso_rt_20221223","https://docs.misoenergy.org/marketreports/20221223_rt_lmp_final.csv"),
 ("miso_da_20250122","https://docs.misoenergy.org/marketreports/20250122_da_expost_lmp.csv"),
 ("ercot_home","https://www.ercot.com/mp/data-products/data-product-details?id=NP4-190-CD"),
]
for n,u in T:
    try:
        rq = urllib.request.Request(u, headers=H)
        try:
            r = urllib.request.urlopen(rq, timeout=60); code=r.status
        except urllib.error.HTTPError as e:
            r = e; code=e.code
        body = r.read(60_000_000)
        ct = r.headers.get("Content-Type","")
        ext = "zip" if "zip" in ct else "csv"
        open(os.path.join(out, n+"."+ext),"wb").write(body)
        print(n, code, ct, len(body), flush=True)
        print("   ", body[:160].replace(bytes([10]),b" | "), flush=True)
    except Exception as e:
        print(n, "ERR", repr(e)[:200], flush=True)
    time.sleep(2)
