"""
Dashboard Generator
====================
Generates a self-contained static HTML dashboard from the SQLite database.
Written to docs/index.html and served via GitHub Pages.

Design: Sand & slate intelligence platform — desert gold, deep navy, warm ivory.
Targets the ME legal market aesthetic.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("dashboard.generator")

DEPT_COLOR = {
    "Corporate / M&A":               "#D4A83C",
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
    "Corporate / M&A":               "🤝",
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
    "recruiter_posting": "Recruiter Posting",
    "lateral_hire":      "Lateral Hire",
    "press_release":     "Press Release",
    "ranking":           "Ranking",
    "website_snapshot":  "Website Change",
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
    "Jeddah":       "🇸🇦",
    "Kuwait":       "🇰🇼",
    "Oman":         "🇴🇲",
    "Muscat":       "🇴🇲",
    "Middle East":  "🌍",
    "DIFC":         "🇦🇪",
    "ADGM":         "🇦🇪",
}


class DashboardGenerator:
    def __init__(self, db):
        self._db = db

    def generate(self, output_path: str = "docs/index.html") -> str:
        weekly_signals = self._db.get_signals_this_week()
        all_signals    = self._db.get_all_signals(limit=300)
        generated_at   = datetime.utcnow()

        # ── Aggregate per firm ────────────────────────────────────────────
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
            d = firms_data[fid]
            w = SIGNAL_WEIGHT.get(sig.get("signal_type", ""), 1.0)
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

        # All recent jobs (all firms)
        all_jobs = [
            s for s in all_signals
            if s.get("signal_type") in ("job_posting", "recruiter_posting")
        ]
        all_jobs.sort(key=lambda s: s.get("created_at", ""), reverse=True)

        html = self._render(ranked, all_jobs, generated_at, weekly_signals)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(html, encoding="utf-8")
        logger.info(f"Dashboard written → {output_path}")
        return output_path

    # ── HTML renderer ─────────────────────────────────────────────────────

    def _render(
        self,
        ranked: list,
        all_jobs: list,
        generated_at: datetime,
        weekly_signals: list,
    ) -> str:

        job_count  = sum(1 for s in weekly_signals if s.get("signal_type") in ("job_posting", "recruiter_posting"))
        hire_count = sum(1 for s in weekly_signals if s.get("signal_type") == "lateral_hire")
        firm_count = len(ranked)

        # ── Firm cards ────────────────────────────────────────────────────
        firm_cards_html = ""
        for i, firm in enumerate(ranked, 1):
            top_dept = max(firm["depts"], key=firm["depts"].get) if firm["depts"] else "N/A"
            color    = DEPT_COLOR.get(top_dept, "#888")
            dept_e   = DEPT_EMOJI.get(top_dept, "⚖️")

            locs_html = " ".join(
                f'<span class="loc-badge">{LOCATION_FLAG.get(l, "📍")} {l}</span>'
                for l in firm["locations"][:5]
            )

            dept_pills = ""
            for dept, cnt in sorted(firm["depts"].items(), key=lambda x: -x[1])[:5]:
                c  = DEPT_COLOR.get(dept, "#888")
                de = DEPT_EMOJI.get(dept, "⚖️")
                dept_pills += (
                    f'<span class="dept-pill" style="border-color:{c};color:{c}">'
                    f'{de} {dept} <b>{cnt}</b></span> '
                )

            # Recent signals
            sig_rows = ""
            for sig in firm["signals"][:6]:
                st  = sig.get("signal_type", "")
                lbl = SIGNAL_LABEL.get(st, st)
                loc = sig.get("location", "")
                loc_flag = LOCATION_FLAG.get(loc, "📍") + " " + loc if loc else ""
                url = sig.get("url", "#")
                sig_rows += f"""
                <div class="sig-row">
                  <span class="sig-badge">{lbl}</span>
                  <a href="{url}" target="_blank" rel="noopener">{sig['title'][:72]}</a>
                  {f'<span class="sig-loc">{loc_flag}</span>' if loc_flag else ''}
                </div>"""

            firm_cards_html += f"""
            <div class="firm-card" style="--accent:{color}" id="firm-{firm['firm_id']}">
              <div class="firm-rank">#{i}</div>
              <div class="firm-header">
                <div class="firm-name">{firm['firm_name']}</div>
                <div class="firm-score">{firm['score']:.1f}</div>
              </div>
              <div class="firm-locs">{locs_html}</div>
              <div class="firm-dept">{dept_e} <strong>{top_dept}</strong></div>
              <div class="firm-pills">{dept_pills}</div>
              <div class="firm-signals">{sig_rows}</div>
            </div>"""

        # ── Jobs board ────────────────────────────────────────────────────
        jobs_html = ""
        for sig in all_jobs[:40]:
            loc      = sig.get("location", "Middle East")
            flag     = LOCATION_FLAG.get(loc, "📍")
            seniority = sig.get("seniority", "Associate")
            dept     = sig.get("department", "")
            dept_c   = DEPT_COLOR.get(dept, "#888")
            dept_e   = DEPT_EMOJI.get(dept, "⚖️")
            via      = f"<span class='via'>via {sig['recruiter']}</span>" if sig.get("recruiter") else ""
            source   = sig.get("source", "")
            date_raw = sig.get("created_at", "")[:10]
            url      = sig.get("url", "#")

            jobs_html += f"""
            <div class="job-card">
              <div class="job-top">
                <span class="job-firm">{sig['firm_name']}</span>
                <span class="job-date">{date_raw}</span>
              </div>
              <a class="job-title" href="{url}" target="_blank" rel="noopener">{sig['title']}</a>
              <div class="job-meta">
                <span class="job-loc">{flag} {loc}</span>
                <span class="job-seniority">👤 {seniority}</span>
                <span class="job-dept" style="color:{dept_c}">{dept_e} {dept}</span>
                {via}
                {f'<span class="job-source">{source}</span>' if source else ''}
              </div>
            </div>"""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>ME Legal Jobs Tracker — US BigLaw in the Middle East</title>
<style>
  :root {{
    --bg:       #0d1117;
    --surface:  #161b22;
    --card:     #1c2230;
    --border:   #30363d;
    --gold:     #d4a83c;
    --text:     #e6e1d5;
    --muted:    #8b949e;
    --green:    #3fb950;
    --radius:   10px;
    --font:     'Inter', 'Segoe UI', sans-serif;
    --mono:     'JetBrains Mono', 'Fira Code', monospace;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: var(--font);
    font-size: 14px;
    line-height: 1.6;
  }}
  a {{ color: var(--gold); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}

  /* Header */
  .header {{
    background: linear-gradient(135deg, #0d1117 0%, #1a2332 100%);
    border-bottom: 1px solid var(--border);
    padding: 24px 32px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
  }}
  .header-title {{ font-size: 22px; font-weight: 700; color: var(--gold); }}
  .header-sub {{ font-size: 13px; color: var(--muted); margin-top: 4px; }}
  .header-meta {{ font-size: 12px; color: var(--muted); text-align: right; }}

  /* KPI strip */
  .kpi-strip {{
    display: flex;
    gap: 12px;
    padding: 16px 32px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    flex-wrap: wrap;
  }}
  .kpi-box {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 12px 20px;
    flex: 1;
    min-width: 140px;
  }}
  .kpi-val {{ font-size: 28px; font-weight: 700; color: var(--gold); }}
  .kpi-lbl {{ font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .6px; margin-top: 4px; }}

  /* Tabs */
  .tabs {{ display: flex; gap: 0; padding: 0 32px; background: var(--surface); border-bottom: 1px solid var(--border); }}
  .tab {{
    padding: 12px 20px;
    cursor: pointer;
    border-bottom: 2px solid transparent;
    font-size: 13px;
    color: var(--muted);
    transition: all .2s;
  }}
  .tab.active {{ color: var(--gold); border-bottom-color: var(--gold); font-weight: 600; }}
  .tab-content {{ display: none; padding: 24px 32px; }}
  .tab-content.active {{ display: block; }}

  /* Firm grid */
  .firms-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 16px;
  }}
  .firm-card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-left: 4px solid var(--accent, var(--gold));
    border-radius: var(--radius);
    padding: 16px;
    position: relative;
  }}
  .firm-rank {{
    position: absolute;
    top: 12px;
    right: 14px;
    font-size: 11px;
    color: var(--muted);
    font-family: var(--mono);
  }}
  .firm-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; }}
  .firm-name {{ font-size: 15px; font-weight: 600; color: var(--text); max-width: 74%; }}
  .firm-score {{ font-size: 20px; font-weight: 700; color: var(--gold); font-family: var(--mono); }}
  .firm-locs {{ display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }}
  .loc-badge {{
    background: #1e2a3a;
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 2px 8px;
    font-size: 11px;
    color: var(--muted);
  }}
  .firm-dept {{ font-size: 12px; color: var(--muted); margin-bottom: 8px; }}
  .firm-pills {{ display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 10px; }}
  .dept-pill {{
    border: 1px solid;
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 11px;
  }}
  .firm-signals {{ display: flex; flex-direction: column; gap: 4px; }}
  .sig-row {{ display: flex; align-items: center; gap: 6px; font-size: 12px; flex-wrap: wrap; }}
  .sig-badge {{
    background: #252d3d;
    border-radius: 4px;
    padding: 1px 6px;
    font-size: 10px;
    color: var(--muted);
    white-space: nowrap;
  }}
  .sig-loc {{ font-size: 11px; color: var(--muted); }}

  /* Jobs board */
  .jobs-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
    gap: 14px;
  }}
  .job-card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 14px;
  }}
  .job-top {{ display: flex; justify-content: space-between; margin-bottom: 4px; }}
  .job-firm {{ font-size: 12px; color: var(--muted); font-weight: 600; }}
  .job-date {{ font-size: 11px; color: var(--muted); }}
  .job-title {{ display: block; font-size: 13px; font-weight: 600; color: var(--text); margin-bottom: 8px; }}
  .job-title:hover {{ color: var(--gold); }}
  .job-meta {{ display: flex; flex-wrap: wrap; gap: 6px; font-size: 11px; }}
  .job-loc, .job-seniority, .job-dept, .via, .job-source {{
    background: #1e2a3a;
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 2px 8px;
    color: var(--muted);
  }}

  /* Footer */
  .footer {{
    text-align: center;
    padding: 24px;
    font-size: 11px;
    color: var(--muted);
    border-top: 1px solid var(--border);
    margin-top: 32px;
  }}
</style>
</head>
<body>

<header class="header">
  <div>
    <div class="header-title">⚖️ ME Legal Jobs Tracker</div>
    <div class="header-sub">US BigLaw associate openings in Dubai · Abu Dhabi · Qatar · Riyadh · Bahrain · Kuwait · Oman</div>
  </div>
  <div class="header-meta">
    Generated {generated_at.strftime("%-d %b %Y, %H:%M")} UTC<br/>
    Tracking {len(ranked)} US firms · {len(all_jobs)} job postings logged
  </div>
</header>

<div class="kpi-strip">
  <div class="kpi-box">
    <div class="kpi-val">{job_count}</div>
    <div class="kpi-lbl">New Jobs (7 days)</div>
  </div>
  <div class="kpi-box">
    <div class="kpi-val">{hire_count}</div>
    <div class="kpi-lbl">Lateral Hire Signals</div>
  </div>
  <div class="kpi-box">
    <div class="kpi-val">{firm_count}</div>
    <div class="kpi-lbl">Active US Firms</div>
  </div>
  <div class="kpi-box">
    <div class="kpi-val">{len(weekly_signals)}</div>
    <div class="kpi-lbl">Total Weekly Signals</div>
  </div>
</div>

<div class="tabs">
  <div class="tab active" onclick="switchTab('firms',this)">🏛 Firm Activity</div>
  <div class="tab" onclick="switchTab('jobs',this)">💼 All Jobs</div>
</div>

<div id="tab-firms" class="tab-content active">
  <div class="firms-grid">
    {firm_cards_html or '<p style="color:var(--muted);padding:24px">No signals yet this week. Run the tracker to populate.</p>'}
  </div>
</div>

<div id="tab-jobs" class="tab-content">
  <div class="jobs-grid">
    {jobs_html or '<p style="color:var(--muted);padding:24px">No job postings logged yet.</p>'}
  </div>
</div>

<div class="footer">
  ME Legal Jobs Tracker — US law firm associate opportunities in the Middle East<br/>
  Data refreshed daily via GitHub Actions · Powered by open-source scrapers
</div>

<script>
function switchTab(name, el) {{
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  el.classList.add('active');
}}
</script>
</body>
</html>"""
