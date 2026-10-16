"""
Generates HistoryReport.html: a self-contained HTML report of play-history
clusters (manufacturer, year/decade, type, rating, recency, monthly trend)
from the PinUP Popper database.

Usage:
    python Vpin_HistoryReport.py [days]

Settings (DB_PATH, TARGET_EMU_IDS, HISTORY_DAYS) come from vpin_recommender_config.py.
Charts use Chart.js from a CDN, so the browser needs internet access.
"""
import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime

from vpin_recommender_config import DB_PATH, TARGET_EMU_IDS as _CFG_EMUS, HISTORY_DAYS, SCRIPT_DIR

# Override without touching config: set VPIN_EMU_IDS=10 (comma-separated)
TARGET_EMU_IDS = os.environ.get("VPIN_EMU_IDS", _CFG_EMUS)

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else int(HISTORY_DAYS)
OUT = os.path.join(SCRIPT_DIR, "HistoryReport.html")

GAMES_QUERY = f"""
SELECT count(1) AS Plays,
       sum(SessionPlayedSecs) AS Secs,
       CAST(JULIANDAY('now') - JULIANDAY(max(cgl.PlayDate)) AS INTEGER) AS LastPlayedDays,
       g.GameID, GameDisplay, GameYear, Manufact, GameType, GameRating
FROM Games g JOIN CustomGameLog cgl ON g.GameID = cgl.GameID
WHERE g.EMUID IN ({TARGET_EMU_IDS}) AND g.visible = 1
  AND PlayDate > DateTime('Now', 'LocalTime', '-' || ? || ' Day')
GROUP BY cgl.GameID
HAVING sum(SessionPlayedSecs) >= 60
"""

MONTHLY_QUERY = f"""
SELECT strftime('%Y-%m', PlayDate) AS Month, count(1) AS Plays, sum(SessionPlayedSecs) AS Secs
FROM Games g JOIN CustomGameLog cgl ON g.GameID = cgl.GameID
WHERE g.EMUID IN ({TARGET_EMU_IDS}) AND g.visible = 1
  AND PlayDate > DateTime('Now', 'LocalTime', '-' || ? || ' Day')
GROUP BY Month ORDER BY Month
"""

CATALOG_QUERY = f"""
SELECT Manufact, GameYear, GameType FROM Games
WHERE EMUID IN ({TARGET_EMU_IDS}) AND visible = 1
"""


def to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def load():
    if not os.path.exists(DB_PATH):
        sys.exit(f"Database not found at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    games = [dict(r) for r in cur.execute(GAMES_QUERY, (DAYS,))]
    monthly = [dict(r) for r in cur.execute(MONTHLY_QUERY, (DAYS,))]
    catalog = [dict(r) for r in cur.execute(CATALOG_QUERY)]
    conn.close()
    for g in games:
        g["Year"] = to_int(g["GameYear"])
        if g["Year"] is not None and not 1930 <= g["Year"] <= datetime.now().year + 1:
            g["Year"] = None
        g["Manufact"] = (g["Manufact"] or "").strip() or "Unknown"
        g["GameType"] = (g["GameType"] or "").strip() or "Unknown"
        r = to_int(g["GameRating"])
        g["Rating"] = r if r and 1 <= r <= 5 else 0
        g["Hours"] = round((g["Secs"] or 0) / 3600, 2)
        g["AvgMin"] = round((g["Secs"] or 0) / g["Plays"] / 60, 1)
        g["Name"] = g["GameDisplay"]
    return games, monthly, catalog


def decade(y):
    return "Unknown" if y is None else f"{y // 10 * 10}s"


def group(games, keyfn):
    out = defaultdict(lambda: {"tables": 0, "plays": 0, "hours": 0.0})
    for g in games:
        o = out[keyfn(g)]
        o["tables"] += 1
        o["plays"] += g["Plays"]
        o["hours"] += g["Hours"]
    return out


def build_payload(games, monthly, catalog):
    by_manu = group(games, lambda g: g["Manufact"])
    manu_rows = sorted(by_manu.items(), key=lambda kv: -kv[1]["hours"])
    top_manus = [m for m, _ in manu_rows[:12]]

    by_year = group([g for g in games if g["Year"]], lambda g: g["Year"])
    years = sorted(by_year)
    by_dec = group(games, lambda g: decade(g["Year"]))
    decs = sorted(by_dec, key=lambda d: (d == "Unknown", d))
    by_type = group(games, lambda g: g["GameType"])
    by_rating = group(games, lambda g: g["Rating"])

    # Manufacturer x decade heatmap (hours)
    heat = defaultdict(lambda: defaultdict(float))
    for g in games:
        m = g["Manufact"] if g["Manufact"] in top_manus else "Other"
        heat[m][decade(g["Year"])] += g["Hours"]
    heat_rows = top_manus + (["Other"] if "Other" in heat else [])

    # Played-vs-owned coverage by manufacturer
    owned = defaultdict(int)
    for c in catalog:
        owned[(c["Manufact"] or "").strip() or "Unknown"] += 1
    coverage = [
        {"manu": m, "owned": owned[m], "played": by_manu[m]["tables"]}
        for m in top_manus if owned.get(m)
    ]

    recency_buckets = [("0-7d", 0, 7), ("8-30d", 8, 30), ("31-90d", 31, 90),
                       ("91-180d", 91, 180), ("181d+", 181, 10 ** 6)]
    recency = [
        {"label": lbl, "tables": sum(1 for g in games if lo <= (g["LastPlayedDays"] or 0) <= hi)}
        for lbl, lo, hi in recency_buckets
    ]

    rounded = lambda d: {k: round(v, 1) if isinstance(v, float) else v for k, v in d.items()}
    return {
        "days": DAYS,
        "summary": {
            "tables": len(games),
            "plays": sum(g["Plays"] for g in games),
            "hours": round(sum(g["Hours"] for g in games), 1),
            "manus": len(by_manu),
            "catalog": len(catalog),
        },
        "manu": [{"name": m, **rounded(v)} for m, v in manu_rows[:15]],
        "years": [{"year": y, **rounded(by_year[y])} for y in years],
        "decades": [{"name": d, **rounded(by_dec[d])} for d in decs],
        "types": [{"name": t, **rounded(v)} for t, v in sorted(by_type.items(), key=lambda kv: -kv[1]["hours"])],
        "ratings": [{"name": "Unrated" if r == 0 else f"{r}★", **rounded(by_rating[r])}
                    for r in sorted(by_rating)],
        "heat": {"rows": heat_rows, "cols": decs,
                 "vals": [[round(heat[r].get(c, 0), 1) for c in decs] for r in heat_rows]},
        "coverage": coverage,
        "recency": recency,
        "monthly": monthly,
        "scatter": [{"x": g["Year"], "y": g["AvgMin"], "r": g["Hours"], "label": g["Name"],
                     "manu": g["Manufact"], "rating": g["Rating"]}
                    for g in games if g["Year"]],
        "top": sorted(
            [{"name": g["Name"], "manu": g["Manufact"], "year": g["Year"], "type": g["GameType"],
              "rating": g["Rating"], "plays": g["Plays"], "hours": g["Hours"],
              "avg": g["AvgMin"], "last": g["LastPlayedDays"]} for g in games],
            key=lambda r: -r["hours"])[:40],
    }


HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>VPin Play History Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<style>
  :root { --bg:#3d3b3a; --surface:#292929; --soft:#2e2e2e; --border:#474747; --text:#f0f0f0;
          --muted:#b5b5b5; --accent:#e0457b; --pt:#4fd1c5; }
  body { margin:0; padding:24px; background:var(--bg); color:var(--text);
         font-family:"Segoe UI",Arial,sans-serif; }
  h1 { margin:0 0 4px; } h2 { margin:0 0 12px; font-size:16px; }
  .sub { color:var(--muted); margin-bottom:20px; }
  .summary { display:flex; gap:14px; flex-wrap:wrap; margin-bottom:20px; }
  .summary div { background:var(--surface); border:1px solid var(--border); border-radius:8px;
                 padding:12px 18px; color:var(--muted); font-size:12px; }
  .summary b { display:block; font-size:22px; color:var(--pt); }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(520px,1fr)); gap:16px; }
  .card { background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:16px; }
  .card.wide { grid-column:1/-1; }
  .chart { position:relative; height:320px; }
  .chart.tall { height:440px; }
  table { border-collapse:collapse; width:100%; font-size:13px; }
  th,td { padding:5px 8px; text-align:right; border-bottom:1px solid var(--border); }
  th:first-child,td:first-child { text-align:left; }
  th { color:var(--muted); position:sticky; top:0; background:var(--surface); cursor:default; }
  .note { color:var(--muted); font-size:12px; margin-top:8px; }
  .scroll { max-height:480px; overflow:auto; }
</style></head><body>
<h1>VPin Play History</h1>
<div class="sub" id="sub"></div>
<div class="summary" id="summary"></div>
<div class="grid">
  <div class="card"><h2>Hours by Manufacturer (top 15)</h2><div class="chart tall"><canvas id="cManu"></canvas></div></div>
  <div class="card"><h2>Hours by Table Year</h2><div class="chart tall"><canvas id="cYear"></canvas></div></div>
  <div class="card"><h2>Monthly Play Trend</h2><div class="chart"><canvas id="cMonth"></canvas></div></div>
  <div class="card"><h2>Hours by Decade</h2><div class="chart"><canvas id="cDec"></canvas></div></div>
  <div class="card"><h2>Hours by Table Type</h2><div class="chart"><canvas id="cType"></canvas></div></div>
  <div class="card"><h2>Tables by Rating</h2><div class="chart"><canvas id="cRate"></canvas></div></div>
  <div class="card"><h2>Tables by Last Played</h2><div class="chart"><canvas id="cRecency"></canvas></div></div>
  <div class="card"><h2>Catalog Coverage: Played vs Owned</h2><div class="chart"><canvas id="cCov"></canvas></div></div>
  <div class="card wide"><h2>Manufacturer &times; Decade Heatmap (hours played)</h2><div id="heat"></div></div>
  <div class="card wide"><h2>Table Year vs Average Session Length</h2>
    <div class="chart tall"><canvas id="cScatter"></canvas></div>
    <div class="note">Bubble size = total hours played. Color = manufacturer (top 8; others grey).</div></div>
  <div class="card wide"><h2>Top 40 Tables by Time Played</h2><div class="scroll" id="top"></div></div>
</div>
<script>
const D = __DATA__;
const PAL = ['#4fd1c5','#e0457b','#f59e0b','#60a5fa','#a78bfa','#34d399','#f87171','#fbbf24','#38bdf8','#c084fc','#fb923c','#94a3b8'];
Chart.defaults.color = '#d0d0d0'; Chart.defaults.borderColor = '#474747';
const fmt = n => n.toLocaleString();
document.getElementById('sub').textContent = `Last ${D.days} days \u00b7 generated ${new Date().toLocaleString()}`;
const S = D.summary;
document.getElementById('summary').innerHTML =
  [['Tables played',S.tables],['of catalog',S.catalog],['Sessions',S.plays],['Hours',S.hours],['Manufacturers',S.manus]]
  .map(([k,v])=>`<div><b>${fmt(v)}</b>${k}</div>`).join('');

const bar = (id, labels, data, o={}) => new Chart(document.getElementById(id), {
  type:'bar', data:{labels, datasets:[{data, backgroundColor:o.colors||PAL[0], label:o.label||'Hours'}]},
  options:{indexAxis:o.horizontal?'y':'x', maintainAspectRatio:false, plugins:{legend:{display:false}}}});

bar('cManu', D.manu.map(r=>r.name), D.manu.map(r=>r.hours), {horizontal:true});
bar('cYear', D.years.map(r=>r.year), D.years.map(r=>r.hours), {colors:PAL[1]});
bar('cDec', D.decades.map(r=>r.name), D.decades.map(r=>r.hours), {colors:PAL[2]});
bar('cType', D.types.map(r=>r.name), D.types.map(r=>r.hours), {colors:PAL[3]});
bar('cRate', D.ratings.map(r=>r.name), D.ratings.map(r=>r.tables), {colors:PAL[4], label:'Tables'});
bar('cRecency', D.recency.map(r=>r.label), D.recency.map(r=>r.tables), {colors:PAL[5], label:'Tables'});

new Chart(document.getElementById('cMonth'), {
  data:{labels:D.monthly.map(r=>r.Month), datasets:[
    {type:'bar', label:'Hours', data:D.monthly.map(r=>+(r.Secs/3600).toFixed(1)), backgroundColor:PAL[0], yAxisID:'y'},
    {type:'line', label:'Sessions', data:D.monthly.map(r=>r.Plays), borderColor:PAL[1], backgroundColor:PAL[1], yAxisID:'y1', tension:.25}]},
  options:{maintainAspectRatio:false, scales:{y:{title:{display:true,text:'Hours'}},
    y1:{position:'right', grid:{drawOnChartArea:false}, title:{display:true,text:'Sessions'}}}}});

new Chart(document.getElementById('cCov'), {
  type:'bar', data:{labels:D.coverage.map(r=>r.manu), datasets:[
    {label:'Owned', data:D.coverage.map(r=>r.owned), backgroundColor:'#5f5f5f'},
    {label:'Played', data:D.coverage.map(r=>r.played), backgroundColor:PAL[0]}]},
  options:{maintainAspectRatio:false}});

const topManus = D.manu.slice(0,8).map(r=>r.name);
const colorOf = m => { const i = topManus.indexOf(m); return i<0 ? '#777' : PAL[i]; };
new Chart(document.getElementById('cScatter'), {
  type:'bubble', data:{datasets:[{data:D.scatter.map(p=>({x:p.x,y:p.y,r:Math.max(3,Math.min(24,Math.sqrt(p.r)*3)),p})),
    backgroundColor:D.scatter.map(p=>colorOf(p.manu)+'aa')}]},
  options:{maintainAspectRatio:false, plugins:{legend:{display:false}, tooltip:{callbacks:{label:c=>{
    const p=c.raw.p; return `${p.label} (${p.manu}, ${p.x}) \u2014 ${p.y} min/session, ${p.r} h`;}}}},
    scales:{x:{title:{display:true,text:'Table year'}}, y:{title:{display:true,text:'Avg session (min)'}}}}});

// Heatmap
(function(){
  const H = D.heat, max = Math.max(1, ...H.vals.flat());
  let h = '<table><tr><th>Manufacturer</th>' + H.cols.map(c=>`<th>${c}</th>`).join('') + '</tr>';
  H.rows.forEach((r,i)=>{ h += `<tr><td>${r}</td>` + H.vals[i].map(v=>{
    const a = v ? (0.12 + 0.88*v/max).toFixed(2) : 0;
    return `<td style="background:rgba(79,209,197,${a});color:${a>0.55?'#111':'inherit'}">${v||''}</td>`;}).join('') + '</tr>'; });
  document.getElementById('heat').innerHTML = h + '</table>';
})();

// Top tables
document.getElementById('top').innerHTML =
  '<table><tr><th>Table</th><th>Manufacturer</th><th>Year</th><th>Type</th><th>Rating</th><th>Sessions</th><th>Hours</th><th>Avg min</th><th>Last played (days)</th></tr>' +
  D.top.map(r=>`<tr><td>${r.name}</td><td>${r.manu}</td><td>${r.year??''}</td><td>${r.type}</td><td>${r.rating?r.rating+'\u2605':''}</td><td>${r.plays}</td><td>${r.hours}</td><td>${r.avg}</td><td>${r.last}</td></tr>`).join('') + '</table>';
</script></body></html>
"""


def main():
    games, monthly, catalog = load()
    if not games:
        sys.exit("No play history found for the configured window.")
    payload = build_payload(games, monthly, catalog)
    data = json.dumps(payload, default=str).replace("</", "<\\/")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(HTML.replace("__DATA__", data))
    print(f"Wrote {OUT} ({payload['summary']['tables']} tables, {DAYS} days)")


if __name__ == "__main__":
    main()
