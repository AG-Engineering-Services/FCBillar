const fs=require('fs');
const S=JSON.parse(fs.readFileSync(require('path').join(__dirname,'..','systems.json')));
function exprVars(expr, vars){ return Object.keys(vars).filter(k => new RegExp("(^|[^A-Za-z0-9_.])"+k+"(?![A-Za-z0-9_])").test(expr)); }
function evalIn(expr, vals, T){ const ks=Object.keys(vals); try{ return Function("T","Math",...ks,`"use strict";return (${expr});`)(T||{},Math,...ks.map(k=>vals[k])); }catch(e){ return {err:e.message}; } }
const pick=a=>a[Math.floor(Math.random()*a.length)];
let bad=0;
for(const s of S){ const c=s.trainer&&s.trainer.calc; if(!c) { if(!(s.trainer&&s.trainer.quiz&&s.trainer.quiz.length)) console.log('NO TRAINER',s.id); continue; }
  c.relations.forEach((r,i)=>{ let ok=0, err=null, miss=null;
    for(let t=0;t<400;t++){ const need=exprVars(r.expr+" "+(r.when||""),c.vars).filter(k=>k!==r.solve); const vals={};
      for(const k of need){ const src=(c.inputs&&c.inputs[k])||(c.vars[k]&&c.vars[k].values); if(!src||!src.length){miss=k;break;} vals[k]=pick(src); }
      if(miss) break;
      if(r.when){ const w=evalIn(r.when,vals,c.tables); if(w&&w.err){err=w.err;break;} if(!w) continue; }
      let v=evalIn(r.expr,vals,c.tables); if(v&&v.err){err=v.err;break;} if(typeof v!=="number"||!isFinite(v)) continue;
      const all={...vals,[r.solve]:v}; if(c.valid){ const full=Object.fromEntries(Object.keys(c.vars).map(k=>[k,k in all?all[k]:null]));const vv=evalIn(c.valid,full,c.tables); if(vv&&vv.err){err=vv.err;break;} if(vv===false) continue; }
      ok++; }
    if(!ok){ bad++; console.log('FAIL',s.id,i,r.solve,'=',r.expr,r.when||'', miss?'missing input '+miss:'', err||''); }
  });
  if(c.path) for(const k of c.path) if(!c.vars[k]) console.log('path var missing',s.id,k);
  for(const k in c.vars){ const v=c.vars[k]; if(v.numbering && !(s.numberings||[]).some(n=>n.name===v.numbering)) console.log('bad numbering',s.id,k,v.numbering); }
}
console.log('bad relations',bad);
