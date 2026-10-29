import sys, collections, struct
sys.path.insert(0, sys.argv[2])
import xls_min as x
w=x.ole_stream(open(sys.argv[1]+"/ice_electric-2014final.xls","rb").read())
rs=list(x.records(w)); print(len(w),len(rs)); print(collections.Counter(hex(t) for t,_ in rs).most_common(15))
n=0
for t,d in rs:
    if t in (0x0203,0x027E,0x0006,0x00BD) and n<6: print(hex(t),len(d),d.hex()); n+=1
