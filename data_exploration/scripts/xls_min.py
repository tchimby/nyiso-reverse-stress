# minimal read-only BIFF8 .xls reader (OLE2 + SST + cells); data parsing only, no execution of file content
import struct, sys
def ole_stream(b, name="Workbook"):
    ss=1<<struct.unpack_from("<H",b,30)[0]; mss=1<<struct.unpack_from("<H",b,32)[0]
    nfat,dirsec,_,cutoff,minifat0,nmf,difat0,ndif=struct.unpack_from("<IIIIIIII",b,44)[0],struct.unpack_from("<I",b,48)[0],0,struct.unpack_from("<I",b,56)[0],struct.unpack_from("<I",b,60)[0],struct.unpack_from("<I",b,64)[0],struct.unpack_from("<I",b,68)[0],struct.unpack_from("<I",b,72)[0]
    difat=list(struct.unpack_from("<109I",b,76))
    sec=lambda i:b[512+i*ss:512+(i+1)*ss] if ss==512 else b[ss+i*ss:ss+(i+1)*ss]
    d=difat0
    while d not in (0xFFFFFFFE,0xFFFFFFFF) and ndif>0:
        s=sec(d); difat+=list(struct.unpack("<%dI"%(ss//4-1),s[:-4])); d=struct.unpack("<I",s[-4:])[0]; ndif-=1
    fat=[]
    for i in difat:
        if i>=0xFFFFFFFA: continue
        fat+=list(struct.unpack("<%dI"%(ss//4),sec(i)))
    def chain(s):
        out=[]
        while s<0xFFFFFFFA: out.append(s); s=fat[s]
        return out
    def read(s): return b"".join(sec(i) for i in chain(s))
    dirb=read(dirsec); ents=[]
    for o in range(0,len(dirb),128):
        e=dirb[o:o+128]; nl=struct.unpack_from("<H",e,64)[0]
        nm=e[:max(nl-2,0)].decode("utf-16le","ignore"); typ=e[66]
        st=struct.unpack_from("<I",e,116)[0]; sz=struct.unpack_from("<I",e,120)[0]; ents.append((nm,typ,st,sz))
    root=ents[0]
    for nm,typ,st,sz in ents:
        if nm==name:
            if sz>=cutoff: return read(st)[:sz]
            mf=[]; s=minifat0
            while s<0xFFFFFFFA: mf+=list(struct.unpack("<%dI"%(ss//4),sec(s))); s=fat[s]
            mini=read(root[2]); out=b""; s=st
            while s<0xFFFFFFFA: out+=mini[s*mss:(s+1)*mss]; s=mf[s]
            return out[:sz]
def records(w):
    o=0
    while o+4<=len(w):
        t,l=struct.unpack_from("<HH",w,o); yield t,w[o+4:o+4+l]; o+=4+l
def rk(v):
    if v&2: x=float(v>>2 if v>>2<0x20000000 else (v>>2)-0x40000000) if False else float(struct.unpack("<i",struct.pack("<I",v))[0]>>2)
    else: x=struct.unpack("<d",struct.pack("<Q",(v&0xFFFFFFFC)<<32))[0]
    return x/100 if v&1 else x
def read_xls(path):
    b=open(path,"rb").read(); w=ole_stream(b)
    recs=list(records(w))
    # merge CONTINUE for SST
    sst=[]; sheets=[]; cur=None; cells={}; 
    i=0
    while i<len(recs):
        t,d=recs[i]
        if t==0x00FC:
            data=d; j=i+1; chunks=[d]
            while j<len(recs) and recs[j][0]==0x003C: chunks.append(recs[j][1]); j+=1
            sst=parse_sst(chunks); i=j; continue
        if t==0x0085: nl=d[6]; flag=d[7]; nm=d[8:8+nl*(2 if flag&1 else 1)].decode("utf-16le" if flag&1 else "latin1"); sheets.append(nm)
        if t==0x0809 and d[2:4]==b"\x10\x00":
            cur=len(cells); cells[cur]={}
        if cur is not None and cur in cells:
            if t==0x00FD: r,c,x,idx=struct.unpack_from("<HHHI",d); cells[cur][(r,c)]=sst[idx]
            elif t==0x0203: r,c,x=struct.unpack_from("<HHH",d); cells[cur][(r,c)]=struct.unpack_from("<d",d,6)[0]
            elif t==0x027E: r,c,x,v=struct.unpack_from("<HHHI",d); cells[cur][(r,c)]=rk(v)
            elif t==0x00BD:
                r,c0=struct.unpack_from("<HH",d); n=(len(d)-6)//6
                for k in range(n): v=struct.unpack_from("<I",d,4+k*6+2)[0]; cells[cur][(r,c0+k)]=rk(v)
        i+=1
    return sheets,cells
def parse_sst(chunks):
    buf=b"".join(chunks); # approximate: ignores continuation flag bytes (ok for ascii-only strings w/o splitting)
    n=struct.unpack_from("<I",buf,4)[0]; o=8; out=[]
    for _ in range(n):
        if o+3>len(buf): break
        cch=struct.unpack_from("<H",buf,o)[0]; fl=buf[o+2]; o+=3
        rt=0; ext=0
        if fl&8: rt=struct.unpack_from("<H",buf,o)[0]; o+=2
        if fl&4: ext=struct.unpack_from("<I",buf,o)[0]; o+=4
        if fl&1: s=buf[o:o+2*cch].decode("utf-16le","ignore"); o+=2*cch
        else: s=buf[o:o+cch].decode("latin1"); o+=cch
        o+=4*rt+ext; out.append(s)
    return out
if __name__=="__main__":
    sh,c=read_xls(sys.argv[1]); print(sh,{k:len(v) for k,v in c.items()})
