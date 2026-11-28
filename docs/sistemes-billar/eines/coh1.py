import json,re,os
S=json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'systems.json')))
num=r'[-+−]?\d+(?:[.,]\d+)?'
op=r'[-+−–×x*/÷]'
pat=re.compile(rf'(\(?(?:{num}\)?\s*{op}\s*\(?)+{num}\)?)\s*=\s*({num})')
def ev(e):
    e=e.replace(',','.').replace('×','*').replace('x','*').replace('−','-').replace('–','-').replace('÷','/')
    try: return eval(e)
    except: return None
for s in S:
    texts=[(e.get('text',''),'ex') for e in s.get('examples') or []]+[(q.get('explain','')+' | '+q.get('q','')+' | '+' / '.join(map(str,q.get('options',[]))),'quiz') for q in (s.get('trainer') or {}).get('quiz') or []]+[(c,'corr') for c in s.get('corrections') or []]+[(c,'step') for c in s.get('steps') or []]+[(c,'tip') for c in s.get('tips') or []]
    for t,k in texts:
        for m in pat.finditer(t):
            l=ev(m.group(1)); r=float(m.group(2).replace(',','.').replace('−','-'))
            if l is not None and abs(l-r)>1e-6: print(s['id'],k,'|',m.group(0),'| calc',round(l,3),'|',t[:150])
