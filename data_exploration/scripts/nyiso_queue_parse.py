import sys,re,subprocess
pdf,first,last=sys.argv[1],sys.argv[2],sys.argv[3]
txt=subprocess.run(['pdftotext','-raw','-f',first,'-l',last,pdf,'-'],capture_output=True,text=True).stdout
rows=[]
for l in txt.splitlines():
    m=re.match(r'^(\d{3,4})\s+(.*?)\s+([A-K])\s+([A-Z][a-z]{2}-\d\d)\s+([\d,.]+)\s+([\d,.]+)\s*(\(.*\))?\s*$',l)
    if m: rows.append((m[1],m[2],m[3],m[4],float(m[5].replace(',','')),float(m[6].replace(',','')),m[7] or ''))
print('n',len(rows),'summer sum',round(sum(r[4] for r in rows),1),'winter sum',round(sum(r[5] for r in rows),1))
inf=[r for r in rows if '(2)' in r[6]]
print('in forecast (note 2) n',len(inf),'MW',round(sum(r[4] for r in inf),1))
kw=re.compile(r'data|compute|digital|ai\b|artificial|datacenter|wulf|mariner|globe|digihost|crypto|sabey|zeroc|databank',re.I)
dc=[r for r in rows if kw.search(r[1])]
print('datacenter-keyword n',len(dc),'MW',round(sum(r[4] for r in dc),1))
mic=[r for r in rows if 'Micron' in r[1]]
print('micron',[(r[0],r[4]) for r in mic])
from collections import defaultdict
z=defaultdict(float)
for r in rows:z[r[2]]+=r[4]
print(dict(sorted(z.items())))
big=sorted(rows,key=lambda r:-r[4])[:5];print([(r[0],r[1][:30],r[4]) for r in big])
