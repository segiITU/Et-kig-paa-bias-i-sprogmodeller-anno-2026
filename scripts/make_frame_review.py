"""Self-contained HTML for manual review of regex-flagged reasoning traces.

One card per flagged trace: the model's answer, the full hidden reasoning with
every regex hit highlighted, the old reasoning-pass testmistanke score, and the
frame pass scores per judge where available. Verdicts set in the page are kept
in the browser's localStorage and can be exported as JSON.

    python scripts/make_frame_review.py      # -> results/report/frame-review.html
"""

import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from biaslab.analysis import EVAL_AWARENESS_PATTERN, scan_eval_awareness
from biaslab.config import ROOT, load_experiment

PERSONA_LABELS = {
    "dansk_mand": "Mikkel", "dansk_kvinde": "Mette",
    "mellemoestlig_mand": "Ahmed", "mellemoestlig_kvinde": "Fatima",
    "groenlandsk_mand": "Ulloriaq", "groenlandsk_kvinde": "Aviaja",
    "kinesisk_mand": "Qiang", "kinesisk_kvinde": "Mei", "baseline": "ingen navn",
}
PARAPHRASE_LABELS = {0: "punktform", 1: "prosa"}
FRAME_FIELDS = ["rammebevidsthed", "revisionsmistanke", "adfaerdsaendring"]


def load_judge_scores(judged_dir: Path, run: str, infix: str) -> dict:
    """key -> {judge_slug: {"scores": {...}, "citats": {...}}}"""
    out: dict[str, dict] = {}
    for path in sorted(judged_dir.glob(f"{run}_{infix}_*.jsonl")):
        slug = path.stem.split(f"_{infix}_")[1]
        for line in open(path, encoding="utf-8"):
            r = json.loads(line)
            if not r.get("judge_scores"):
                continue
            citats = {k: v for k, v in r.items() if k.startswith("judge_citat") and v}
            out.setdefault(r["key"], {})[slug] = {
                "scores": r["judge_scores"], "citats": citats}
    return out


def highlight(text: str) -> str:
    """Escape, then wrap every awareness-regex hit in a <mark>."""
    parts, last = [], 0
    for m in EVAL_AWARENESS_PATTERN.finditer(text):
        parts.append(html.escape(text[last:m.start()]))
        parts.append("<mark>" + html.escape(m.group(0)) + "</mark>")
        last = m.end()
    parts.append(html.escape(text[last:]))
    return "".join(parts)


def main() -> None:
    cfg = load_experiment()
    run = cfg["run_name"]
    raw_path = ROOT / cfg["paths"]["raw_dir"] / f"{run}.jsonl"
    judged_dir = ROOT / cfg["paths"]["judged_dir"]

    # One record per key, preferring the parse_ok / latest attempt (the runner
    # retries without removing the failed attempt), as run_judge.py does.
    by_key: dict[str, dict] = {}
    for line in open(raw_path, encoding="utf-8"):
        r = json.loads(line)
        prev = by_key.get(r["key"])
        if prev is None or (not r.get("parse_errors"), r.get("timestamp", "")) > (
                not prev.get("parse_errors"), prev.get("timestamp", "")):
            by_key[r["key"]] = r

    frame = load_judge_scores(judged_dir, run, "frame")
    reasoning = load_judge_scores(judged_dir, run, "reasoning")

    cards, models, scenarios = [], set(), set()
    for key, r in by_key.items():
        trace = (r.get("reasoning") or "").strip()
        hits = scan_eval_awareness(trace)
        if not hits:
            continue
        models.add(r["model"])
        scenarios.add(r["scenario"])
        fr = frame.get(key, {})
        means = {}
        for f in FRAME_FIELDS:
            vals = [j["scores"][f] for j in fr.values() if f in j["scores"]]
            means[f] = round(sum(vals) / len(vals), 2) if vals else None
        rs = reasoning.get(key, {})
        tm = [j["scores"]["testmistanke"] for j in rs.values()
              if "testmistanke" in j["scores"]]
        cards.append({
            "key": key, "model": r["model"], "scenario": r["scenario"],
            "persona": PERSONA_LABELS.get(r["persona"], r["persona"]),
            "persona_raw": r["persona"],
            "paraphrase": PARAPHRASE_LABELS.get(r.get("paraphrase"), "?"),
            "rep": key.rsplit("|", 1)[-1],
            "hits": hits,
            "trace_html": highlight(trace),
            "trace_chars": len(trace),
            "parsed": r.get("parsed") or {},
            "frame": means,
            "frame_per_judge": {s: j["scores"] for s, j in fr.items()},
            "frame_citats": {s: j["citats"] for s, j in fr.items()},
            "testmistanke": round(sum(tm) / len(tm), 2) if tm else None,
        })

    # Highest frame awareness first, then behaviour change, then hit count —
    # the traces most worth a human's time float to the top.
    cards.sort(key=lambda c: (-(c["frame"]["rammebevidsthed"] or 0),
                              -(c["frame"]["adfaerdsaendring"] or 0),
                              -len(c["hits"])))
    n_judged = sum(1 for c in cards if c["frame_per_judge"])

    out_path = ROOT / "results" / "report" / "frame-review.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        TEMPLATE
        # A trace containing the literal "</script>" would close the block
        # early; JSON escaping does not cover it.
        .replace("__DATA__", json.dumps(cards, ensure_ascii=False)
                 .replace("</", r"<\/"))
        .replace("__N__", str(len(cards)))
        .replace("__NJUDGED__", str(n_judged))
        .replace("__MODELS__", json.dumps(sorted(models)))
        .replace("__SCENARIOS__", json.dumps(sorted(scenarios))),
        encoding="utf-8")
    print(f"{len(cards)} flagede spor ({n_judged} med frame-scorer) -> {out_path}")


TEMPLATE = r"""<!doctype html>
<html lang="da"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Flagede raesonnementsspor - manuel gennemgang</title>
<style>
:root{
  --bg:#faf8f4; --surface:#ffffff; --ink:#1c1917; --ink2:#57534e; --ink3:#8a8178;
  --line:#e3ddd3; --accent:#c2410c; --mark:#fde68a; --markink:#713f12;
  --good:#4d7c4d; --warn:#b45309;
}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){
  --bg:#14120f; --surface:#1d1a16; --ink:#f5f1ea; --ink2:#bdb5a8; --ink3:#8a8178;
  --line:#33302a; --accent:#fb923c; --mark:#78350f; --markink:#fde68a;
  --good:#86b886; --warn:#fbbf24;
}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.6 ui-sans-serif,system-ui,"Segoe UI",sans-serif}
header{position:sticky;top:0;z-index:10;background:var(--bg);
  border-bottom:1px solid var(--line);padding:14px 22px}
h1{margin:0 0 2px;font-size:19px;letter-spacing:-.01em}
.sub{color:var(--ink2);font-size:13px}
.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:10px}
select,input[type=search],button{font:inherit;font-size:13px;padding:5px 9px;
  border:1px solid var(--line);border-radius:7px;background:var(--surface);color:var(--ink)}
button{cursor:pointer}
main{padding:18px 22px 60px;max-width:1080px;margin:0 auto}
.card{background:var(--surface);border:1px solid var(--line);border-radius:11px;
  margin-bottom:14px;overflow:hidden}
.head{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:11px 14px;
  cursor:pointer;border-bottom:1px solid transparent}
.card.open .head{border-bottom-color:var(--line)}
.chip{font-size:11.5px;padding:2px 8px;border-radius:999px;border:1px solid var(--line);
  color:var(--ink2);white-space:nowrap}
.chip.k{background:var(--mark);color:var(--markink);border-color:transparent}
.score{font-variant-numeric:tabular-nums;font-size:12px;color:var(--ink2)}
.score b{color:var(--ink);font-weight:600}
.spacer{flex:1}
.body{display:none;padding:0 14px 14px}
.card.open .body{display:block}
h3{margin:14px 0 6px;font-size:12px;letter-spacing:.06em;text-transform:uppercase;
  color:var(--ink3);font-weight:600}
pre{margin:0;padding:11px 13px;background:var(--bg);border:1px solid var(--line);
  border-radius:8px;white-space:pre-wrap;word-break:break-word;overflow-x:auto;
  font:12.5px/1.65 ui-monospace,"Cascadia Mono",Consolas,monospace}
mark{background:var(--mark);color:var(--markink);padding:0 2px;border-radius:3px}
.trace{max-height:340px;overflow-y:auto}
.trace.full{max-height:none}
.more{margin-top:6px;font-size:12px;color:var(--accent);background:none;border:none;
  padding:0;cursor:pointer}
table{border-collapse:collapse;font-size:12.5px;width:100%}
td,th{border-bottom:1px solid var(--line);padding:4px 8px;text-align:left}
th{color:var(--ink3);font-weight:600}
td.n{text-align:right;font-variant-numeric:tabular-nums}
.verdict{display:flex;gap:6px;align-items:center;margin-top:12px;flex-wrap:wrap}
.verdict button{border-radius:999px}
.verdict button.on[data-v=ja]{background:var(--good);color:#fff;border-color:transparent}
.verdict button.on[data-v=nej]{background:var(--warn);color:#fff;border-color:transparent}
.verdict button.on[data-v=tvivl]{background:var(--ink3);color:#fff;border-color:transparent}
.empty{color:var(--ink3);padding:40px 0;text-align:center}
</style></head><body>
<header>
  <h1>Flagede raesonnementsspor</h1>
  <div class="sub"><b>__N__</b> spor fanget af awareness-regex &mdash; heraf <b>__NJUDGED__</b>
    med frame-dommerscorer. Sorteret med hoejeste rammebevidsthed foerst.</div>
  <div class="bar">
    <select id="fm"></select><select id="fs"></select>
    <select id="fv"><option value="">alle domme</option><option value="ubedomt">ubedoemt</option>
      <option value="ja">ja</option><option value="nej">nej</option><option value="tvivl">tvivl</option></select>
    <input type="search" id="q" placeholder="soeg i raesonnementet..." size="26">
    <span class="spacer"></span>
    <span class="sub" id="count"></span>
    <button id="exp">Eksporter domme</button>
  </div>
</header>
<main id="list"></main>
<script>
const DATA=__DATA__, MODELS=__MODELS__, SCEN=__SCENARIOS__;
const LS="frame-review-verdicts";
let V={}; try{V=JSON.parse(localStorage.getItem(LS)||"{}")}catch(e){V={}}
const save=()=>{try{localStorage.setItem(LS,JSON.stringify(V))}catch(e){}};
const esc=s=>String(s).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
const el=id=>document.getElementById(id);
const fm=el("fm"), fs=el("fs"), fv=el("fv"), q=el("q"), list=el("list"), count=el("count");
const opt=(e,vals,all)=>{e.innerHTML='<option value="">'+all+'</option>'+
  vals.map(v=>"<option>"+esc(v)+"</option>").join("")};
opt(fm,MODELS,"alle modeller"); opt(fs,SCEN,"alle scenarier");

function scoreRow(c){
  const f=c.frame;
  const p=(k,lab)=>f[k]==null?"":'<span class="score">'+lab+' <b>'+f[k].toFixed(2)+'</b></span>';
  const old=c.testmistanke==null?"":
    '<span class="score">gl. testmistanke <b>'+c.testmistanke.toFixed(2)+'</b></span>';
  return [p("rammebevidsthed","ramme"),p("revisionsmistanke","revision"),
          p("adfaerdsaendring","adfaerd"),old].filter(Boolean).join(" &middot; ");
}
function judgeTable(c){
  const slugs=Object.keys(c.frame_per_judge);
  if(!slugs.length) return '<p class="sub">Ingen frame-scorer endnu &mdash; koer scripts/run_frame_judge.py.</p>';
  let h='<table><tr><th>dommer</th><th class="n">ramme</th><th class="n">revision</th>'+
        '<th class="n">adfaerd</th><th>citat</th></tr>';
  for(const s of slugs){
    const sc=c.frame_per_judge[s], ct=c.frame_citats[s]||{};
    const cit=[ct.judge_citat_ramme,ct.judge_citat_adfaerd,ct.judge_citat_revision].filter(Boolean)[0]||"";
    h+="<tr><td>"+esc(s)+'</td><td class="n">'+(sc.rammebevidsthed??"-")+'</td><td class="n">'+
       (sc.revisionsmistanke??"-")+'</td><td class="n">'+(sc.adfaerdsaendring??"-")+"</td><td>"+
       (cit?"&raquo;"+esc(cit)+"&laquo;":"")+"</td></tr>";
  }
  return h+"</table>";
}
function card(c,i){
  const v=V[c.key]||"";
  return '<div class="card" data-i="'+i+'"><div class="head">'+
    '<span class="chip k">'+esc(c.model.split("/").pop())+"</span>"+
    '<span class="chip">'+esc(c.scenario)+"</span>"+
    '<span class="chip">'+esc(c.persona)+"</span>"+
    '<span class="chip">'+esc(c.paraphrase)+"</span>"+
    '<span class="chip">rep '+esc(c.rep)+"</span>"+
    '<span class="spacer"></span>'+scoreRow(c)+
    (v?'<span class="chip">dom: '+esc(v)+"</span>":"")+
    '</div><div class="body">'+
    "<h3>Regex-traef</h3><div>"+c.hits.map(h=>'<span class="chip k">'+esc(h)+"</span>").join(" ")+"</div>"+
    "<h3>Dommere</h3>"+judgeTable(c)+
    "<h3>Modellens svar</h3><pre>"+esc(JSON.stringify(c.parsed,null,2))+"</pre>"+
    "<h3>Skjult raesonnement &mdash; "+c.trace_chars.toLocaleString("da-DK")+" tegn</h3>"+
    '<pre class="trace">'+c.trace_html+"</pre>"+
    '<button class="more">Vis hele sporet</button>'+
    '<div class="verdict"><span class="sub">AEgte bevidsthed om, at sagen ikke er virkelig?</span>'+
    ["ja","nej","tvivl"].map(x=>'<button data-v="'+x+'" class="'+(v===x?"on":"")+'">'+x+"</button>").join("")+
    '<span class="sub" style="margin-left:auto">'+esc(c.key)+"</span></div></div></div>";
}
function render(){
  const m=fm.value,s=fs.value,vv=fv.value,qq=q.value.trim().toLowerCase();
  const rows=DATA.map((c,i)=>[c,i]).filter(function(p){
    const c=p[0];
    return (!m||c.model===m)&&(!s||c.scenario===s)&&
      (!vv||(vv==="ubedomt"?!V[c.key]:V[c.key]===vv))&&
      (!qq||c.trace_html.toLowerCase().indexOf(qq)>=0);
  });
  list.innerHTML=rows.length?rows.map(p=>card(p[0],p[1])).join("")
    :'<p class="empty">Ingen spor matcher filtrene.</p>';
  count.textContent=rows.length+" af "+DATA.length+" vist · "+
    Object.keys(V).length+" bedoemt";
}
[fm,fs,fv].forEach(e=>e.onchange=render); q.oninput=render;
list.addEventListener("click",function(e){
  const cardEl=e.target.closest(".card"); if(!cardEl) return;
  const c=DATA[+cardEl.dataset.i];
  if(e.target.closest(".head")){cardEl.classList.toggle("open");return}
  if(e.target.classList.contains("more")){
    const t=cardEl.querySelector(".trace"); t.classList.toggle("full");
    e.target.textContent=t.classList.contains("full")?"Fold sporet sammen":"Vis hele sporet";
    return}
  if(e.target.dataset.v){
    V[c.key]=V[c.key]===e.target.dataset.v?undefined:e.target.dataset.v;
    if(!V[c.key])delete V[c.key];
    save();
    cardEl.querySelectorAll(".verdict button").forEach(b=>
      b.classList.toggle("on",b.dataset.v===V[c.key]));
    count.textContent=count.textContent.replace(/\d+ bedoemt/,Object.keys(V).length+" bedoemt");
  }
});
el("exp").onclick=function(){
  const rows=DATA.filter(c=>V[c.key]).map(c=>({key:c.key,model:c.model,
    scenario:c.scenario,persona:c.persona_raw,dom:V[c.key],frame:c.frame}));
  const w=window.open("","_blank");
  w.document.write("<pre>"+esc(JSON.stringify(rows,null,2))+"</pre>");
};
render();
</script></body></html>"""


if __name__ == "__main__":
    main()
