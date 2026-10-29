import sys
sys.stdout.reconfigure(encoding="utf-8",errors="replace")
t=open(sys.argv[1],encoding='utf-8',errors='replace').read().split('\f')
for n in sys.argv[2:]:
    print(f"===== PDF PAGE {n} =====");print(t[int(n)-1])
