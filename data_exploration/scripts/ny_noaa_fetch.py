import sys, time, os, requests
out = sys.argv[1]
st = {"NYC_CentralPark":"USW00094728","LGA":"USW00014732","JFK":"USW00094789","ALB":"USW00014735","BUF":"USW00014733","SYR":"USW00014771"}
for k,v in st.items():
    r=requests.get(f"https://www.ncei.noaa.gov/data/daily-summaries/access/{v}.csv",timeout=180)
    print(k,v,r.status_code,len(r.content))
    if r.status_code==200: open(os.path.join(out,f"{k}_{v}.csv"),"wb").write(r.content)
    time.sleep(1.5)
