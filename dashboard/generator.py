"""
Dashboard Generator  (v3)
==========================
ADDED: Chart.js bar chart — Practice Areas in Demand (last 30 days)
ADDED: Pie chart — Signal type breakdown
ADDED: Regulatory filings signal type
FIXED: Vercel URL hardcoded throughout
"""
import json, logging, os
from datetime import datetime
from pathlib import Path
from learning.evolution import get_top4_departments

logger = logging.getLogger("dashboard.generator")

DEPT_COLOR = {
    "Corporate / M&A":                "#D4A83C",
    "Banking & Finance":              "#5BA8D4",
    "Capital Markets":                "#4B8EC4",
    "Project Finance & Infrastructure":"#8A9BBD",
    "Energy & Natural Resources":     "#E07845",
    "Real Estate":                    "#5BBD8A",
    "Arbitration & Disputes":         "#D45B5B",
    "Islamic Finance":                "#6BBD6B",
    "Private Equity & Funds":         "#F07C3E",
    "Regulatory & Compliance":        "#A87ED4",
    "Employment & Labour":            "#5BBDBD",
    "Data Privacy & Technology":      "#D45B8A",
    "Construction & Engineering":     "#BD8A6B",
    "Restructuring & Insolvency":     "#E07845",
}
DEPT_EMOJI = {
    "Corporate / M&A":"🤝","Banking & Finance":"🏦","Capital Markets":"📈",
    "Project Finance & Infrastructure":"🏗️","Energy & Natural Resources":"⚡",
    "Real Estate":"🏢","Arbitration & Disputes":"⚖️","Islamic Finance":"☪️",
    "Private Equity & Funds":"💰","Regulatory & Compliance":"📋",
    "Employment & Labour":"👷","Data Privacy & Technology":"🔒",
    "Construction & Engineering":"🔧","Restructuring & Insolvency":"🔄",
}
SIGNAL_LABEL = {
    "job_posting":"Job Posting","recruiter_posting":"Recruiter",
    "lateral_hire":"Lateral Hire","press_release":"Press Release",
    "ranking":"Ranking","regulatory_filing":"Regulatory Filing",
    "website_snapshot":"Site Change",
}
SIGNAL_WEIGHT = {
    "regulatory_filing": 4.5,
    "recruiter_posting": 4.0,
    "lateral_hire":      3.5,
    "ranking":           3.0,
    "job_posting":       2.5,
    "website_snapshot":  2.0,
    "press_release":     2.0,
}
LOCATION_FLAG = {
    "Dubai":"🇦🇪","Abu Dhabi":"🇦🇪","UAE":"🇦🇪","Qatar":"🇶🇦","Doha":"🇶🇦",
    "Bahrain":"🇧🇭","Manama":"🇧🇭","Saudi Arabia":"🇸🇦","Riyadh":"🇸🇦",
    "Kuwait":"🇰🇼","Muscat":"🇴🇲","Oman":"🇴🇲","Middle East":"🌍",
    "DIFC":"🇦🇪","ADGM":"🇦🇪",
}
MEDALS = ["🥇","🥈","🥉","4️⃣"]
VERCEL = "https://middle-east-jobs-tracker.vercel.app/"
CHART_CDN = "https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"


class DashboardGenerator:
    def __init__(self, db):
        self._db = db

    def generate(self, output_path: str = "docs/index.html") -> str:
        weekly_signals = self._db.get_signals_this_week()
        all_signals    = self._db.get_all_signals(limit=500)
        generated_at   = datetime.utcnow()
        top4           = get_top4_departments()

        training_stats = {}
        if os.path.exists("learned_weights.json"):
            try:
                with open("learned_weights.json") as f:
                    training_stats = json.load(f)
            except Exception:
                pass

        geo_data = {}
        if os.path.exists("learning/geo_report.json"):
            try:
                with open("learning/geo_report.json") as f:
                    geo_data = json.load(f)
            except Exception:
                pass

        accuracy_data = {}
        if os.path.exists("learning/accuracy_report.json"):
            try:
                with open("learning/accuracy_report.json") as f:
                    accuracy_data = json.load(f)
            except Exception:
                pass

        # Aggregate per firm
        firms_data: dict = {}
        for sig in weekly_signals:
            fid = sig["firm_id"]
            if fid not in firms_data:
                firms_data[fid] = {
                    "firm_id":fid,"firm_name":sig["firm_name"],
                    "score":0.0,"signals":[],"depts":{},"locations":set(),"jobs":[],
                }
            d = firms_data[fid]
            w = SIGNAL_WEIGHT.get(sig.get("signal_type",""), 1.0)
            d["score"] += w * float(sig.get("department_score", 1.0))
            d["signals"].append(sig)
            dept = sig.get("department","Other")
            d["depts"][dept] = d["depts"].get(dept, 0) + 1
            if sig.get("location"): d["locations"].add(sig["location"])
            if sig.get("signal_type") in ("job_posting","recruiter_posting"):
                d["jobs"].append(sig)

        ranked = sorted(firms_data.values(), key=lambda x: x["score"], reverse=True)
        for r in ranked: r["locations"] = list(r["locations"])

        all_jobs = sorted(
            [s for s in all_signals if s.get("signal_type") in ("job_posting","recruiter_posting")],
            key=lambda s: s.get("created_at",""), reverse=True
        )

        # Chart data: dept counts across all recent signals
        dept_counts: dict = {}
        signal_type_counts: dict = {}
        for sig in all_signals[:300]:
            d = sig.get("department","Other")
            if d: dept_counts[d] = dept_counts.get(d, 0) + 1
            t = sig.get("signal_type","other")
            label = SIGNAL_LABEL.get(t, t)
            signal_type_counts[label] = signal_type_counts.get(label, 0) + 1

        # Geo chart data from geo_report
        geo_cities = geo_data.get("cities", [])[:8]

        # Sort dept_counts
        dept_sorted = sorted(dept_counts.items(), key=lambda x: -x[1])[:10]

        html = self._render(ranked, all_jobs, generated_at, weekly_signals,
                            top4, training_stats, dept_sorted, signal_type_counts,
                            geo_cities, accuracy_data)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(html, encoding="utf-8")
        logger.info(f"Dashboard written → {output_path}")
        return output_path

    def _render(self, ranked, all_jobs, generated_at, weekly_signals,
                top4, training_stats, dept_sorted, signal_type_counts,
                geo_cities=None, accuracy_data=None):
        job_count  = sum(1 for s in weekly_signals if s.get("signal_type") in ("job_posting","recruiter_posting"))
        hire_count = sum(1 for s in weekly_signals if s.get("signal_type") == "lateral_hire")
        reg_count  = sum(1 for s in weekly_signals if s.get("signal_type") == "regulatory_filing")
        firm_count = len(ranked)
        ts         = generated_at.strftime("%d %b %Y %H:%M UTC")
        train_runs = training_stats.get("total_runs", 0)
        last_train = (training_stats.get("last_trained","")[:10]) or "Not yet"
        acc_pct    = accuracy_data.get("accuracy_pct", None) if accuracy_data else None
        acc_html   = (f'<span class="acc-badge">🎯 {acc_pct:.0%} accurate</span>'
                      if acc_pct is not None else "")

        # ── Top 4 cards ───────────────────────────────────────────────────
        top4_html = ""
        for i, dept in enumerate(top4[:4]):
            d_name  = dept.get("department","")
            d_count = dept.get("signal_count", 0)
            d_firms = dept.get("firm_count", 0)
            d_boost = dept.get("trend_boost", 1.0)
            color   = DEPT_COLOR.get(d_name, "#888")
            emoji   = DEPT_EMOJI.get(d_name,"")
            medal   = MEDALS[i] if i < len(MEDALS) else f"#{i+1}"
            trend_cls = "trend-up" if d_boost > 1.02 else ("trend-dn" if d_boost < 0.98 else "trend-flat")
            trend_sym = "↑" if trend_cls=="trend-up" else ("↓" if trend_cls=="trend-dn" else "→")
            top4_html += (
                f'<div class="top4-card" style="--t4c:{color}">'
                f'<div class="t4-medal">{medal}</div>'
                f'<div class="t4-emoji">{emoji}</div>'
                f'<div class="t4-name">{d_name}</div>'
                f'<div class="t4-stats">'
                f'<span class="t4-count">{d_count} signals</span>'
                f'<span class="t4-firms">{d_firms} firm(s)</span>'
                f'<span class="t4-trend {trend_cls}">{trend_sym}</span>'
                f'</div></div>'
            )
        if not top4_html:
            top4_html = '<p class="muted">Training data builds after first run.</p>'

        # ── Chart.js data ─────────────────────────────────────────────────
        bar_labels  = json.dumps([d[0] for d in dept_sorted])
        bar_values  = json.dumps([d[1] for d in dept_sorted])
        bar_colors  = json.dumps([DEPT_COLOR.get(d[0],"#888") for d in dept_sorted])

        pie_labels  = json.dumps(list(signal_type_counts.keys()))
        pie_values  = json.dumps(list(signal_type_counts.values()))
        pie_colors  = json.dumps([
            "#D4A83C","#5BA8D4","#D45B5B","#5BBD8A",
            "#A87ED4","#F07C3E","#5BBDBD","#D45B8A",
        ][:len(signal_type_counts)])

        # Geo bar chart
        geo_cities = geo_cities or []
        geo_labels = json.dumps([c["city"] for c in geo_cities])
        geo_values = json.dumps([c["this_week"] for c in geo_cities])
        geo_colors = json.dumps([
            "#D4A83C" if c.get("trend","").startswith("↑") else
            "#5BA8D4" if c.get("trend","").startswith("→") else "#D45B5B"
            for c in geo_cities
        ])

        # ── Firm cards ────────────────────────────────────────────────────
        firm_cards_html = ""
        for i, firm in enumerate(ranked, 1):
            top_dept = max(firm["depts"], key=firm["depts"].get) if firm["depts"] else "N/A"
            color    = DEPT_COLOR.get(top_dept, "#888")
            dept_e   = DEPT_EMOJI.get(top_dept, "")
            locs_html = " ".join(
                f'<span class="loc-badge">{LOCATION_FLAG.get(l,"📍")} {l}</span>'
                for l in firm["locations"][:5]
            )
            dept_pills = ""
            for dept, cnt in sorted(firm["depts"].items(), key=lambda x:-x[1])[:5]:
                c = DEPT_COLOR.get(dept,"#888")
                de = DEPT_EMOJI.get(dept,"")
                dept_pills += f'<span class="dept-pill" style="border-color:{c};color:{c}">{de} {dept} <b>{cnt}</b></span> '
            sig_rows = ""
            for sig in firm["signals"][:6]:
                st  = sig.get("signal_type","")
                lbl = SIGNAL_LABEL.get(st, st)
                loc = sig.get("location","")
                loc_str = LOCATION_FLAG.get(loc,"📍")+" "+loc if loc else ""
                url = sig.get("url","#")
                t2  = sig["title"][:72].replace("<","&lt;").replace(">","&gt;")
                sig_rows += (
                    f'<div class="sig-row">'
                    f'<span class="sig-badge">{lbl}</span>'
                    f'<a href="{url}" target="_blank" rel="noopener">{t2}</a>'
                    + (f'<span class="sig-loc">{loc_str}</span>' if loc_str else "")
                    + '</div>'
                )
            firm_cards_html += (
                f'<div class="firm-card" style="--accent:{color}" id="firm-{firm["firm_id"]}">'
                f'<div class="firm-rank">#{i}</div>'
                f'<div class="firm-header"><div class="firm-name">{firm["firm_name"]}</div>'
                f'<div class="firm-score">{firm["score"]:.1f}</div></div>'
                f'<div class="firm-locs">{locs_html}</div>'
                f'<div class="firm-dept">{dept_e} <strong>{top_dept}</strong></div>'
                f'<div class="firm-pills">{dept_pills}</div>'
                f'<div class="firm-signals">{sig_rows}</div></div>'
            )

        # ── Jobs board ────────────────────────────────────────────────────
        jobs_html = ""
        for sig in all_jobs[:50]:
            loc      = sig.get("location","Middle East")
            flag     = LOCATION_FLAG.get(loc,"📍")
            sen      = sig.get("seniority","Associate")
            dept     = sig.get("department","")
            dept_c   = DEPT_COLOR.get(dept,"#888")
            dept_e   = DEPT_EMOJI.get(dept,"")
            via      = f'<span class="via">via {sig["recruiter"]}</span>' if sig.get("recruiter") else ""
            src      = sig.get("source","")
            date_raw = sig.get("created_at","")[:10]
            url      = sig.get("url","#")
            t2       = sig["title"].replace("<","&lt;").replace(">","&gt;")
            jobs_html += (
                f'<div class="job-card">'
                f'<div class="job-top"><span class="job-firm">{sig["firm_name"]}</span>'
                f'<span class="job-date">{date_raw}</span></div>'
                f'<a class="job-title" href="{url}" target="_blank" rel="noopener">{t2}</a>'
                f'<div class="job-meta">'
                f'<span class="job-loc">{flag} {loc}</span>'
                f'<span class="job-sen">👤 {sen}</span>'
                f'<span class="job-dept" style="color:{dept_c}">{dept_e} {dept}</span>'
                + via
                + (f'<span class="job-src">{src}</span>' if src else "")
                + '</div></div>'
            )

        css = self._css()

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>ME Legal Jobs Tracker</title>
<script src="{CHART_CDN}"></script>
<style>{css}</style>
</head>
<body>
<div class="header">
  <div class="header-left"><h1>⚖️ ME Legal Jobs Tracker</h1><p>US BigLaw associate openings &amp; ME expansion intelligence</p></div>
  <div class="header-right">Updated {ts}<br><a href="{VERCEL}" target="_blank">🖥 Live Dashboard</a></div>
</div>
<div class="stats-bar">
  <div class="stat-box"><div class="val">{firm_count}</div><div class="lbl">Active Firms</div></div>
  <div class="stat-box"><div class="val">{job_count}</div><div class="lbl">Jobs This Week</div></div>
  <div class="stat-box"><div class="val">{hire_count}</div><div class="lbl">Lateral Hires</div></div>
  <div class="stat-box"><div class="val">{reg_count}</div><div class="lbl">Regulatory Filings</div></div>
  <div class="stat-box"><div class="val">{len(all_jobs)}</div><div class="lbl">Total Jobs Logged</div></div>
  <div class="stat-box ai-box"><div class="val">{train_runs}</div><div class="lbl">AI Training Cycles</div>{acc_html}</div>
</div>

<div class="section">
  <div class="section-title">📊 Top 4 ME Practice Areas in Demand</div>
  <div class="top4-grid">{top4_html}</div>
</div>

<div class="charts-row">
  <div class="chart-card">
    <div class="chart-title">📊 Practice Areas — Signal Volume (Last 30 Days)</div>
    <div class="chart-wrap"><canvas id="barChart"></canvas></div>
  </div>
  <div class="chart-card">
    <div class="chart-title">🍕 Signal Type Breakdown</div>
    <div class="chart-wrap chart-pie-wrap"><canvas id="pieChart"></canvas></div>
  </div>
</div>
<div class="charts-row single">
  <div class="chart-card">
    <div class="chart-title">🌍 Geographic Hotspots — This Week's Signal Volume by City</div>
    <div class="chart-wrap chart-geo-wrap"><canvas id="geoChart"></canvas></div>
  </div>
</div>

<div class="tabs">
  <button class="tab active" onclick="showTab('firms',this)">🏛 Firm Activity</button>
  <button class="tab" onclick="showTab('jobs',this)">💼 Jobs Board</button>
</div>
<div id="tab-firms" class="tab-panel active">
  <div class="firms-grid">{firm_cards_html or '<p class="muted" style="padding:24px">No signals yet. Run the tracker to populate.</p>'}</div>
</div>
<div id="tab-jobs" class="tab-panel">
  <div class="jobs-grid">{jobs_html or '<p class="muted" style="padding:24px">No jobs logged yet.</p>'}</div>
</div>

<div class="footer">
  <span>ME Legal Jobs Tracker · <a href="{VERCEL}">Vercel Dashboard</a></span>
  <span>AI self-training: {train_runs} cycles · Last: {last_train}</span>
</div>

<script>
function showTab(id,btn){{
  document.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.getElementById('tab-'+id).classList.add('active');
  btn.classList.add('active');
}}

// ── Bar chart ────────────────────────────────────────────────────────────
const barCtx = document.getElementById('barChart').getContext('2d');
new Chart(barCtx, {{
  type: 'bar',
  data: {{
    labels: {bar_labels},
    datasets: [{{
      label: 'Signals',
      data: {bar_values},
      backgroundColor: {bar_colors},
      borderColor: {bar_colors},
      borderWidth: 1,
      borderRadius: 4,
    }}]
  }},
  options: {{
    indexAxis: 'y',
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{ callbacks: {{ label: ctx => ' ' + ctx.parsed.x + ' signals' }} }}
    }},
    scales: {{
      x: {{
        beginAtZero: true,
        grid: {{ color: 'rgba(255,255,255,0.05)' }},
        ticks: {{ color: '#8A95A8', font: {{ size: 11 }} }}
      }},
      y: {{
        grid: {{ display: false }},
        ticks: {{ color: '#E8E4D8', font: {{ size: 11 }} }}
      }}
    }}
  }}
}});

// ── Pie / doughnut chart ─────────────────────────────────────────────────
const pieCtx = document.getElementById('pieChart').getContext('2d');
new Chart(pieCtx, {{
  type: 'doughnut',
  data: {{
    labels: {pie_labels},
    datasets: [{{
      data: {pie_values},
      backgroundColor: {pie_colors},
      borderColor: '#162033',
      borderWidth: 2,
      hoverOffset: 6,
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{
        position: 'right',
        labels: {{ color: '#E8E4D8', font: {{ size: 11 }}, boxWidth: 14, padding: 10 }}
      }},
      tooltip: {{
        callbacks: {{
          label: ctx => ' ' + ctx.label + ': ' + ctx.parsed + ' signals'
        }}
      }}
    }}
  }}
}});

// ── Geo hotspot bar chart ─────────────────────────────────────────────────
const geoCtx = document.getElementById('geoChart').getContext('2d');
new Chart(geoCtx, {{
  type: 'bar',
  data: {{
    labels: {geo_labels},
    datasets: [{{
      label: 'Signals this week',
      data: {geo_values},
      backgroundColor: {geo_colors},
      borderRadius: 5,
      borderWidth: 0,
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{ callbacks: {{ label: ctx => ' ' + ctx.parsed.y + ' signals this week' }} }}
    }},
    scales: {{
      x: {{
        grid: {{ display: false }},
        ticks: {{ color: '#E8E4D8', font: {{ size: 12 }} }}
      }},
      y: {{
        beginAtZero: true,
        grid: {{ color: 'rgba(255,255,255,0.05)' }},
        ticks: {{ color: '#8A95A8', font: {{ size: 11 }}, precision: 0 }}
      }}
    }}
  }}
}});
</script>
</body>
</html>"""

    def _css(self) -> str:
        return """
:root{--bg:#0E1624;--card:#162033;--card2:#1C293F;--gold:#D4A83C;--text:#E8E4D8;--muted:#8A95A8;--border:#253348;--red:#D45B5B;--green:#5BBD8A;--blue:#5BA8D4;font-size:15px}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;min-height:100vh}
a{color:var(--gold);text-decoration:none}a:hover{text-decoration:underline}
.header{background:linear-gradient(135deg,#0A1020 0%,#162033 100%);border-bottom:1px solid var(--border);padding:20px 28px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px}
.header-left h1{font-size:1.35rem;font-weight:700;color:var(--gold)}.header-left p{font-size:.78rem;color:var(--muted);margin-top:3px}.header-right{font-size:.75rem;color:var(--muted);text-align:right}
.stats-bar{display:flex;gap:14px;padding:16px 28px;background:var(--card);border-bottom:1px solid var(--border);flex-wrap:wrap}
.stat-box{background:var(--card2);border:1px solid var(--border);border-radius:8px;padding:10px 16px;min-width:100px}
.stat-box .val{font-size:1.4rem;font-weight:700;color:var(--gold)}.stat-box .lbl{font-size:.7rem;color:var(--muted);margin-top:2px}
.ai-box{border-color:rgba(212,168,60,.3)}.acc-badge{display:inline-block;margin-top:4px;font-size:.68rem;color:var(--green);background:rgba(91,189,138,.1);border:1px solid rgba(91,189,138,.3);border-radius:3px;padding:1px 5px}
.section{padding:20px 28px}
.section-title{font-size:.85rem;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:14px;display:flex;align-items:center;gap:8px}
.section-title::after{content:"";flex:1;height:1px;background:var(--border)}
.top4-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
.top4-card{background:var(--card);border:1px solid var(--border);border-top:3px solid var(--t4c,var(--gold));border-radius:10px;padding:14px 16px;display:flex;flex-direction:column;gap:5px;transition:transform .15s}
.top4-card:hover{transform:translateY(-2px)}.t4-medal{font-size:1.25rem}.t4-emoji{font-size:1.5rem;margin-top:2px}
.t4-name{font-size:.88rem;font-weight:600;color:var(--text);line-height:1.3}.t4-stats{display:flex;gap:8px;flex-wrap:wrap;margin-top:4px}
.t4-count{font-size:.8rem;color:var(--gold);font-weight:600}.t4-firms{font-size:.73rem;color:var(--muted)}.t4-trend{font-size:.85rem;font-weight:700}
.trend-up{color:var(--green)}.trend-dn{color:var(--red)}.trend-flat{color:var(--muted)}.muted{color:var(--muted);font-size:.85rem}
.charts-row{display:grid;grid-template-columns:2fr 1fr;gap:16px;padding:0 28px 20px}
.charts-row.single{grid-template-columns:1fr}
.chart-card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:18px}
.chart-title{font-size:.82rem;font-weight:600;color:var(--muted);margin-bottom:14px;text-transform:uppercase;letter-spacing:.5px}
.chart-wrap{height:260px;position:relative}.chart-pie-wrap{height:240px}.chart-geo-wrap{height:200px}
@media(max-width:800px){.charts-row{grid-template-columns:1fr}.charts-row.single{grid-template-columns:1fr}}
.tabs{display:flex;padding:0 28px;background:var(--card);border-bottom:1px solid var(--border)}
.tab{padding:13px 20px;font-size:.85rem;font-weight:600;cursor:pointer;border-bottom:3px solid transparent;color:var(--muted);transition:color .15s,border-color .15s;background:none;border-top:none;border-left:none;border-right:none}
.tab.active{color:var(--gold);border-bottom-color:var(--gold)}.tab-panel{display:none}.tab-panel.active{display:block}
.firms-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:16px;padding:20px 28px}
.firm-card{background:var(--card);border:1px solid var(--border);border-left:4px solid var(--accent,var(--gold));border-radius:10px;padding:18px;transition:box-shadow .15s}
.firm-card:hover{box-shadow:0 4px 20px rgba(0,0,0,.4)}.firm-rank{font-size:.73rem;color:var(--muted);font-weight:700;margin-bottom:6px}
.firm-header{display:flex;justify-content:space-between;margin-bottom:8px}.firm-name{font-size:1rem;font-weight:700;color:var(--text)}.firm-score{font-size:1.1rem;font-weight:700;color:var(--gold)}
.firm-locs{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:8px}.loc-badge{background:rgba(212,168,60,.1);color:var(--gold);border:1px solid rgba(212,168,60,.2);border-radius:4px;font-size:.7rem;padding:2px 7px}
.firm-dept{font-size:.82rem;color:var(--muted);margin-bottom:8px}.firm-pills{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:10px}
.dept-pill{border:1px solid;border-radius:4px;font-size:.7rem;padding:2px 7px}.sig-row{display:flex;gap:8px;font-size:.77rem;margin-bottom:5px;flex-wrap:wrap;align-items:flex-start}
.sig-badge{background:var(--card2);border:1px solid var(--border);color:var(--muted);border-radius:3px;padding:1px 5px;font-size:.68rem;white-space:nowrap;flex-shrink:0}
.sig-loc{color:var(--muted);font-size:.7rem;white-space:nowrap}
.jobs-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:14px;padding:20px 28px}
.job-card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px;transition:box-shadow .15s}.job-card:hover{box-shadow:0 4px 16px rgba(0,0,0,.35)}
.job-top{display:flex;justify-content:space-between;margin-bottom:7px}.job-firm{font-size:.77rem;font-weight:700;color:var(--gold)}.job-date{font-size:.7rem;color:var(--muted)}
.job-title{display:block;font-size:.88rem;font-weight:600;color:var(--text);margin-bottom:8px;line-height:1.35}.job-meta{display:flex;flex-wrap:wrap;gap:8px;font-size:.73rem}
.job-loc{color:var(--blue)}.job-sen{color:var(--muted)}.job-src{color:var(--muted);background:var(--card2);border-radius:3px;padding:1px 5px}.via{color:var(--muted);font-style:italic}
.footer{padding:14px 28px;border-top:1px solid var(--border);font-size:.7rem;color:var(--muted);display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}
"""
