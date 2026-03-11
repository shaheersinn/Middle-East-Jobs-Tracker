"""
Dashboard Generator  (v2)
==========================
ADDED: Top 4 ME practice areas panel (data-driven, self-trained)
ADDED: Self-training stats footer
Dashboard URL: https://middle-east-jobs-tracker.vercel.app/
"""

import json
import logging
import os
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
    "Corporate / M&A":                "🤝",
    "Banking & Finance":              "🏦",
    "Capital Markets":                "📈",
    "Project Finance & Infrastructure":"🏗️",
    "Energy & Natural Resources":     "⚡",
    "Real Estate":                    "🏢",
    "Arbitration & Disputes":         "⚖️",
    "Islamic Finance":                "☪️",
    "Private Equity & Funds":         "💰",
    "Regulatory & Compliance":        "📋",
    "Employment & Labour":            "👷",
    "Data Privacy & Technology":      "🔒",
    "Construction & Engineering":     "🔧",
    "Restructuring & Insolvency":     "🔄",
}

SIGNAL_LABEL = {
    "job_posting":       "Job Posting",
    "recruiter_posting": "Recruiter",
    "lateral_hire":      "Lateral Hire",
    "press_release":     "Press Release",
    "ranking":           "Ranking",
    "website_snapshot":  "Site Change",
}

SIGNAL_WEIGHT = {
    "recruiter_posting": 4.0,
    "lateral_hire":      3.5,
    "ranking":           3.0,
    "job_posting":       2.5,
    "website_snapshot":  2.0,
    "press_release":     2.0,
}

LOCATION_FLAG = {
    "Dubai":        "🇦🇪",
    "Abu Dhabi":    "🇦🇪",
    "UAE":          "🇦🇪",
    "Qatar":        "🇶🇦",
    "Doha":         "🇶🇦",
    "Bahrain":      "🇧🇭",
    "Manama":       "🇧🇭",
    "Saudi Arabia": "🇸🇦",
    "Riyadh":       "🇸🇦",
    "Kuwait":       "🇰🇼",
    "Muscat":       "🇴🇲",
    "Oman":         "🇴🇲",
    "Middle East":  "🌍",
    "DIFC":         "🇦🇪",
    "ADGM":         "🇦🇪",
}

MEDAL = ["🥇", "🥈", "🥉", "4️⃣"]


class DashboardGenerator:
    def __init__(self, db):
        self._db = db

    def generate(self, output_path: str = "docs/index.html") -> str:
        weekly_signals = self._db.get_signals_this_week()
        all_signals    = self._db.get_all_signals(limit=400)
        generated_at   = datetime.utcnow()
        top4           = get_top4_departments()

        # Load self-training stats
        training_stats = {}
        if os.path.exists("learned_weights.json"):
            try:
                with open("learned_weights.json") as f:
                    training_stats = json.load(f)
            except Exception:
                pass

        firms_data: dict = {}
        for sig in weekly_signals:
            fid = sig["firm_id"]
            if fid not in firms_data:
                firms_data[fid] = {
                    "firm_id":   fid,
                    "firm_name": sig["firm_name"],
                    "score":     0.0,
                    "signals":   [],
                    "depts":     {},
                    "locations": set(),
                    "jobs":      [],
                }
            d  = firms_data[fid]
            w  = SIGNAL_WEIGHT.get(sig.get("signal_type", ""), 1.0)
            d["score"] += w * float(sig.get("department_score", 1.0))
            d["signals"].append(sig)
            dept = sig.get("department", "Other")
            d["depts"][dept] = d["depts"].get(dept, 0) + 1
            if sig.get("location"):
                d["locations"].add(sig["location"])
            if sig.get("signal_type") in ("job_posting", "recruiter_posting"):
                d["jobs"].append(sig)

        ranked = sorted(firms_data.values(), key=lambda x: x["score"], reverse=True)
        for r in ranked:
            r["locations"] = list(r["locations"])

        all_jobs = [
            s for s in all_signals
            if s.get("signal_type") in ("job_posting", "recruiter_posting")
        ]
        all_jobs.sort(key=lambda s: s.get("created_at", ""), reverse=True)

        html = self._render(ranked, all_jobs, generated_at, weekly_signals, top4, training_stats)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(html, encoding="utf-8")
        logger.info(f"Dashboard written → {output_path}")
        return output_path

    def _render(self, ranked, all_jobs, generated_at, weekly_signals, top4, training_stats):
        job_count  = sum(1 for s in weekly_signals if s.get("signal_type") in ("job_posting","recruiter_posting"))
        hire_count = sum(1 for s in weekly_signals if s.get("signal_type") == "lateral_hire")
        firm_count = len(ranked)
        ts         = generated_at.strftime("%d %b %Y %H:%M UTC")
        train_runs = training_stats.get("total_runs", 0)
        last_train = (training_stats.get("last_trained","")[:10]) or "Not yet run"

        # Top 4 practice areas
        top4_html = ""
        medals = ["\U0001f947","\U0001f948","\U0001f949","4\ufe0f\u20e3"]
        for i, dept in enumerate(top4[:4]):
            d_name  = dept.get("department", "")
            d_count = dept.get("signal_count", 0)
            d_firms = dept.get("firm_count", 0)
            d_boost = dept.get("trend_boost", 1.0)
            color   = DEPT_COLOR.get(d_name, "#888")
            emoji   = DEPT_EMOJI.get(d_name, "")
            medal   = medals[i] if i < len(medals) else f"#{i+1}"
            trend_arrow = "up" if d_boost > 1.02 else ("down" if d_boost < 0.98 else "flat")
            trend_sym   = "\u2191" if trend_arrow == "up" else ("\u2193" if trend_arrow == "down" else "\u2192")
            top4_html += (
                f'<div class="top4-card" style="--t4c:{color}">'
                f'<div class="t4-medal">{medal}</div>'
                f'<div class="t4-emoji">{emoji}</div>'
                f'<div class="t4-name">{d_name}</div>'
                f'<div class="t4-stats">'
                f'<span class="t4-count">{d_count} signals</span>'
                f'<span class="t4-firms">{d_firms} firm(s)</span>'
                f'<span class="t4-trend trend-{trend_arrow}">{trend_sym}</span>'
                f'</div></div>'
            )

        if not top4_html:
            top4_html = '<p class="muted">Training data will appear after first run.</p>'

        # Firm cards
        firm_cards_html = ""
        for i, firm in enumerate(ranked, 1):
            top_dept = max(firm["depts"], key=firm["depts"].get) if firm["depts"] else "N/A"
            color    = DEPT_COLOR.get(top_dept, "#888")
            dept_e   = DEPT_EMOJI.get(top_dept, "")

            locs_html = " ".join(
                f'<span class="loc-badge">{LOCATION_FLAG.get(l,"&#128205;")} {l}</span>'
                for l in firm["locations"][:5]
            )
            dept_pills = ""
            for dept, cnt in sorted(firm["depts"].items(), key=lambda x: -x[1])[:5]:
                c  = DEPT_COLOR.get(dept, "#888")
                de = DEPT_EMOJI.get(dept, "")
                dept_pills += (
                    f'<span class="dept-pill" style="border-color:{c};color:{c}">'
                    f'{de} {dept} <b>{cnt}</b></span> '
                )
            sig_rows = ""
            for sig in firm["signals"][:6]:
                st      = sig.get("signal_type","")
                lbl     = SIGNAL_LABEL.get(st, st)
                loc     = sig.get("location","")
                loc_str = LOCATION_FLAG.get(loc,"&#128205;") + " " + loc if loc else ""
                url     = sig.get("url","#")
                title_s = sig["title"][:72].replace("<","&lt;").replace(">","&gt;")
                sig_rows += (
                    f'<div class="sig-row">'
                    f'<span class="sig-badge">{lbl}</span>'
                    f'<a href="{url}" target="_blank" rel="noopener">{title_s}</a>'
                    + (f'<span class="sig-loc">{loc_str}</span>' if loc_str else "") +
                    f'</div>'
                )

            firm_cards_html += (
                f'<div class="firm-card" style="--accent:{color}" id="firm-{firm["firm_id"]}">'
                f'<div class="firm-rank">#{i}</div>'
                f'<div class="firm-header">'
                f'<div class="firm-name">{firm["firm_name"]}</div>'
                f'<div class="firm-score">{firm["score"]:.1f}</div></div>'
                f'<div class="firm-locs">{locs_html}</div>'
                f'<div class="firm-dept">{dept_e} <strong>{top_dept}</strong></div>'
                f'<div class="firm-pills">{dept_pills}</div>'
                f'<div class="firm-signals">{sig_rows}</div>'
                f'</div>'
            )

        # Jobs board
        jobs_html = ""
        for sig in all_jobs[:50]:
            loc       = sig.get("location","Middle East")
            flag      = LOCATION_FLAG.get(loc,"&#128205;")
            seniority = sig.get("seniority","Associate")
            dept      = sig.get("department","")
            dept_c    = DEPT_COLOR.get(dept,"#888")
            dept_e    = DEPT_EMOJI.get(dept,"")
            via       = f"<span class='via'>via {sig['recruiter']}</span>" if sig.get("recruiter") else ""
            source    = sig.get("source","")
            date_raw  = sig.get("created_at","")[:10]
            url       = sig.get("url","#")
            title_s   = sig["title"].replace("<","&lt;").replace(">","&gt;")

            jobs_html += (
                f'<div class="job-card">'
                f'<div class="job-top">'
                f'<span class="job-firm">{sig["firm_name"]}</span>'
                f'<span class="job-date">{date_raw}</span></div>'
                f'<a class="job-title" href="{url}" target="_blank" rel="noopener">{title_s}</a>'
                f'<div class="job-meta">'
                f'<span class="job-loc">{flag} {loc}</span>'
                f'<span class="job-seniority">&#128100; {seniority}</span>'
                f'<span class="job-dept" style="color:{dept_c}">{dept_e} {dept}</span>'
                + via
                + (f'<span class="job-source">{source}</span>' if source else "")
                + f'</div></div>'
            )

        css = """
:root{--bg:#0E1624;--card:#162033;--card2:#1C293F;--gold:#D4A83C;--gold2:#F0C660;--text:#E8E4D8;--muted:#8A95A8;--border:#253348;--red:#D45B5B;--green:#5BBD8A;--blue:#5BA8D4;font-size:15px}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;min-height:100vh}
a{color:var(--gold);text-decoration:none} a:hover{text-decoration:underline}
.header{background:linear-gradient(135deg,#0A1020 0%,#162033 100%);border-bottom:1px solid var(--border);padding:20px 28px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px}
.header-left h1{font-size:1.35rem;font-weight:700;color:var(--gold)}
.header-left p{font-size:.78rem;color:var(--muted);margin-top:3px}
.header-right{font-size:.75rem;color:var(--muted);text-align:right}
.stats-bar{display:flex;gap:16px;padding:16px 28px;background:var(--card);border-bottom:1px solid var(--border);flex-wrap:wrap}
.stat-box{background:var(--card2);border:1px solid var(--border);border-radius:8px;padding:12px 18px;min-width:110px}
.stat-box .val{font-size:1.5rem;font-weight:700;color:var(--gold)}
.stat-box .lbl{font-size:.72rem;color:var(--muted);margin-top:2px}
.section{padding:22px 28px}
.section-title{font-size:.85rem;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:14px;display:flex;align-items:center;gap:8px}
.section-title::after{content:"";flex:1;height:1px;background:var(--border)}
.top4-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px}
.top4-card{background:var(--card);border:1px solid var(--border);border-top:3px solid var(--t4c,var(--gold));border-radius:10px;padding:16px 18px;display:flex;flex-direction:column;gap:6px;transition:transform .15s}
.top4-card:hover{transform:translateY(-2px)}
.t4-medal{font-size:1.3rem} .t4-emoji{font-size:1.6rem;margin-top:2px}
.t4-name{font-size:.9rem;font-weight:600;color:var(--text);line-height:1.3}
.t4-stats{display:flex;gap:10px;align-items:center;margin-top:4px;flex-wrap:wrap}
.t4-count{font-size:.82rem;color:var(--gold);font-weight:600}
.t4-firms{font-size:.75rem;color:var(--muted)}
.t4-trend{font-size:.9rem;font-weight:700}
.trend-up{color:var(--green)} .trend-down{color:var(--red)} .trend-flat{color:var(--muted)}
.muted{color:var(--muted);font-size:.85rem}
.tabs{display:flex;gap:0;padding:0 28px;background:var(--card);border-bottom:1px solid var(--border)}
.tab{padding:13px 22px;font-size:.85rem;font-weight:600;cursor:pointer;border-bottom:3px solid transparent;color:var(--muted);transition:color .15s,border-color .15s;background:none;border-top:none;border-left:none;border-right:none}
.tab.active{color:var(--gold);border-bottom-color:var(--gold)}
.tab-panel{display:none} .tab-panel.active{display:block}
.firms-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:16px;padding:22px 28px}
.firm-card{background:var(--card);border:1px solid var(--border);border-left:4px solid var(--accent,var(--gold));border-radius:10px;padding:18px;transition:box-shadow .15s}
.firm-card:hover{box-shadow:0 4px 20px rgba(0,0,0,.4)}
.firm-rank{font-size:.75rem;color:var(--muted);font-weight:700;margin-bottom:6px}
.firm-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px}
.firm-name{font-size:1rem;font-weight:700;color:var(--text)} .firm-score{font-size:1.1rem;font-weight:700;color:var(--gold)}
.firm-locs{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:8px}
.loc-badge{background:rgba(212,168,60,.12);color:var(--gold);border:1px solid rgba(212,168,60,.25);border-radius:4px;font-size:.72rem;padding:2px 7px}
.firm-dept{font-size:.82rem;color:var(--muted);margin-bottom:8px}
.firm-pills{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:10px}
.dept-pill{border:1px solid;border-radius:4px;font-size:.72rem;padding:2px 7px}
.sig-row{display:flex;align-items:flex-start;gap:8px;font-size:.78rem;margin-bottom:5px;flex-wrap:wrap}
.sig-badge{background:var(--card2);border:1px solid var(--border);color:var(--muted);border-radius:3px;padding:1px 5px;white-space:nowrap;flex-shrink:0;font-size:.7rem}
.sig-loc{color:var(--muted);font-size:.72rem;white-space:nowrap}
.jobs-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:14px;padding:22px 28px}
.job-card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px;transition:box-shadow .15s}
.job-card:hover{box-shadow:0 4px 16px rgba(0,0,0,.35)}
.job-top{display:flex;justify-content:space-between;margin-bottom:7px}
.job-firm{font-size:.78rem;font-weight:700;color:var(--gold)} .job-date{font-size:.72rem;color:var(--muted)}
.job-title{display:block;font-size:.9rem;font-weight:600;color:var(--text);margin-bottom:9px;line-height:1.35}
.job-meta{display:flex;flex-wrap:wrap;gap:8px;font-size:.75rem}
.job-loc{color:var(--blue)} .job-seniority{color:var(--muted)}
.job-source{color:var(--muted);background:var(--card2);border-radius:3px;padding:1px 5px}
.via{color:var(--muted);font-style:italic}
.footer{padding:16px 28px;border-top:1px solid var(--border);font-size:.72rem;color:var(--muted);display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}
"""

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>ME Legal Jobs Tracker</title>
<style>{css}</style>
</head>
<body>
<div class="header">
  <div class="header-left"><h1>&#9878; ME Legal Jobs Tracker</h1><p>US BigLaw associate openings &amp; ME expansion signals</p></div>
  <div class="header-right">Updated {ts}<br><a href="https://middle-east-jobs-tracker.vercel.app/" target="_blank">&#128421; Live Dashboard</a></div>
</div>
<div class="stats-bar">
  <div class="stat-box"><div class="val">{firm_count}</div><div class="lbl">Active Firms</div></div>
  <div class="stat-box"><div class="val">{job_count}</div><div class="lbl">Jobs This Week</div></div>
  <div class="stat-box"><div class="val">{hire_count}</div><div class="lbl">Lateral Hires</div></div>
  <div class="stat-box"><div class="val">{len(all_jobs)}</div><div class="lbl">Total Jobs Logged</div></div>
  <div class="stat-box"><div class="val">{train_runs}</div><div class="lbl">Training Cycles</div></div>
</div>
<div class="section">
  <div class="section-title">&#128202; Top 4 ME Practice Areas in Demand</div>
  <div class="top4-grid">{top4_html}</div>
</div>
<div class="tabs">
  <button class="tab active" onclick="showTab('firms',this)">&#127981; Firm Activity</button>
  <button class="tab" onclick="showTab('jobs',this)">&#128188; Jobs Board</button>
</div>
<div id="tab-firms" class="tab-panel active">
  <div class="firms-grid">{firm_cards_html or '<p class="muted" style="padding:24px">No signals yet. Run the tracker to populate.</p>'}</div>
</div>
<div id="tab-jobs" class="tab-panel">
  <div class="jobs-grid">{jobs_html or '<p class="muted" style="padding:24px">No job postings logged yet.</p>'}</div>
</div>
<div class="footer">
  <span>ME Legal Jobs Tracker &middot; <a href="https://middle-east-jobs-tracker.vercel.app/">Vercel Dashboard</a></span>
  <span>Self-training: {train_runs} cycles &middot; Last trained: {last_train}</span>
</div>
<script>
function showTab(id,btn){{document.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));document.getElementById('tab-'+id).classList.add('active');btn.classList.add('active');}}
</script>
</body>
</html>"""
        return html
