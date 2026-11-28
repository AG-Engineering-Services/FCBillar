import json,glob,re,os
BASE=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP={'quotes','id'}
REPL=[(r'\bLlegades\b','Arribades'),(r'\bllegades\b','arribades'),(r'\bLlegadas\b','Arribades'),(r'\bllegadas\b','arribades'),
      (r'\bLlegada\b','Arribada'),(r'\bllegada\b','arribada'),
      (r'\bRombos\b','Diamants'),(r'\brombos\b','diamants'),(r'\bRombo\b','Diamant'),(r'\brombo\b','diamant'),
      (r'\bBricole\b','Bricola'),(r'\bbricole\b','bricola'),(r'\bbricoles\b','bricoles')]
def norm_str(t):
    parts=re.split(r'(«[^»]*»)',t)
    out=[]
    for p in parts:
        if p.startswith('«'): out.append(p); continue
        for a,b in REPL: p=re.sub(a,b,p)
        out.append(p)
    return ''.join(out)
def walk(o,key=None):
    if key in SKIP: return o
    if isinstance(o,str): return norm_str(o)
    if isinstance(o,list): return [walk(x) for x in o]
    if isinstance(o,dict): return {k:walk(v,k) for k,v in o.items()}
    return o
out=[];bad=[]
for f in sorted(glob.glob(os.path.join(BASE,'systems','*.json'))):
    try: d=json.load(open(f)); out.append(walk(d))
    except Exception as e: bad.append((f,str(e)))
json.dump(out,open(os.path.join(BASE,'systems.json'),'w'),ensure_ascii=False,separators=(',',':'))
print(len(out),'systems',bad)
