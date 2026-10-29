import sys,re
sys.stdout.reconfigure(encoding="utf-8",errors="replace")
f,pat=sys.argv[1],sys.argv[2]
ctx=int(sys.argv[3]) if len(sys.argv)>3 else 0
t=open(f,encoding='utf-8',errors='replace').read().split('\f')
for i,p in enumerate(t,1):
    L=p.split('\n')
    for j,l in enumerate(L):
        if re.search(pat,l,re.I):
            print(f"[pdfpage {i}] "+" | ".join(x.strip() for x in L[max(0,j-ctx):j+ctx+1] if x.strip())[:600])
