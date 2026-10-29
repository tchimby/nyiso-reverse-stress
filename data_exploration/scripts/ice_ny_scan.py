import sys, pandas as pd, os
for f in sys.argv[1:]:
    d = pd.read_excel(f, header=0)
    c = d.columns[0]
    print("==", os.path.basename(f), d.shape)
    print(d[c].value_counts().to_string())
    ny = d[d[c].astype(str).str.contains("NY|New York|Zone|NYISO|Iroquois|Transco|Algonquin|Tetco|Texas Eastern|Mass|Nepool|Hudson|Millwood|Marcy", case=False, regex=True)]
    print("NY-like rows:", len(ny), sorted(ny[c].unique()))
