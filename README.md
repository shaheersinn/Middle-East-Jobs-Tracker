# ⚖️ ME Legal Jobs Tracker

Tracks **21 US law firms** across **7 ME job board / recruiter scrapers** and **14 practice departments** — surfacing associate and lawyer job postings, recruiter activity, and lateral hire signals across Dubai, Abu Dhabi, Qatar, Riyadh, Bahrain, Kuwait and Oman.

Runs automatically on **GitHub Actions**. Sends **instant Telegram alerts** on new associate openings and a **ranked weekly digest** every Sunday.

---

## Architecture

### 7 Scrapers (per firm)

| Scraper | Sources | Signal Type | Weight |
|---|---|---|---|
| `JobsScraper` | Firm ME office careers pages (all 21 firms) | `job_posting` | 2.5 |
| `JobBoardsScraper` | Bayt.com · NaukriGulf · GulfTalent · Indeed UAE · LinkedIn ME | `job_posting` | 2.5 |
| `RecruiterScraper` | Kershaw Leonard · Michael Page Legal · Taylor Root · Robert Half · Anton Murray · Charterhouse · Cooper Fitch · Guildhall · Heidrick | `recruiter_posting` | 4.0 |
| `PressScraper` | Firm news · The Lawyer MEA · IFLR ME · Arabian Business | `press_release` / `lateral_hire` | 2.0–3.5 |
| `ChambersScraper` | Chambers Global ME · Legal 500 Middle East | `ranking` | 3.0 |
| `RSSFeedScraper` | 15+ RSS feeds (legal media + firm feeds) | `job_posting` / `lateral_hire` | 2.0–3.5 |
| `WebsiteScraper` | ME office pages + people pages — change detection | `website_snapshot` | 2.0 |

### Signal Confidence Tiers

```
TIER 1 (weight 4.0)  recruiter_posting
  A recruiter is actively being paid to fill the role — highest confidence.

TIER 2 (weight 3.0–3.5)  lateral_hire · ranking
  Confirmed person movement or independent validation.

TIER 3 (weight 2.0–2.5)  job_posting · website_snapshot · press_release
  Observable, verifiable activity.
```

### 14 Practice Departments (ME-focused)

```
Corporate / M&A          Banking & Finance         Capital Markets
Project Finance          Energy & Natural Resources Real Estate
Arbitration & Disputes   Islamic Finance            Private Equity & Funds
Regulatory & Compliance  Employment & Labour        Data Privacy & Technology
Construction & Engineering  Restructuring & Insolvency
```

### 21 Tracked US Firms (with ME offices)

| Firm | HQ | ME Cities | AmLaw |
|---|---|---|---|
| Dentons US LLP | Washington DC | Dubai · Abu Dhabi · Riyadh · Doha · Kuwait · Manama · Muscat | #2 |
| Latham & Watkins | Los Angeles | Dubai · Abu Dhabi · Riyadh | #3 |
| Baker McKenzie | Chicago | Dubai · Abu Dhabi · Manama · Riyadh · Doha | #5 |
| DLA Piper | Washington DC | Dubai · Abu Dhabi · Qatar · Bahrain · Saudi Arabia | #4 |
| Greenberg Traurig | Miami | Dubai | #6 |
| Skadden | New York | Abu Dhabi | #7 |
| A&O Shearman | New York | Dubai · Abu Dhabi · Riyadh | #8 |
| Jones Day | Cleveland | Dubai · Riyadh | #9 |
| Simpson Thacher | New York | Dubai | #11 |
| Sullivan & Cromwell | New York | Abu Dhabi | #12 |
| Gibson Dunn | Los Angeles | Dubai · Riyadh | #14 |
| White & Case | New York | Dubai · Abu Dhabi · Riyadh | #15 |
| Norton Rose Fulbright | Houston | Dubai · Abu Dhabi · Riyadh · Manama · Doha · Kuwait | #16 |
| Milbank | New York | Dubai · Abu Dhabi | #18 |
| McDermott | Chicago | Dubai · Riyadh | #25 |
| Hogan Lovells | Washington DC | Dubai · Abu Dhabi · Riyadh | #26 |
| Mayer Brown | Chicago | Dubai | #30 |
| Reed Smith | Pittsburgh | Dubai · Abu Dhabi · Manama · Riyadh | #28 |
| Squire Patton Boggs | Washington DC | Dubai · Abu Dhabi · Doha · Riyadh | #35 |
| King & Spalding | Atlanta | Dubai · Abu Dhabi · Riyadh | #22 |
| Kirkland & Ellis | Chicago | Dubai | #1 |

### ME Locations Covered

🇦🇪 Dubai (DIFC) · Abu Dhabi (ADGM) · Sharjah  
🇶🇦 Qatar (QFC / Doha)  
🇧🇭 Bahrain (Manama)  
🇸🇦 Saudi Arabia (Riyadh · Jeddah · NEOM)  
🇰🇼 Kuwait  
🇴🇲 Oman (Muscat)

---

## Quick Start

### 1. Create GitHub repo

```bash
gh repo create me-legal-jobs-tracker --private
git clone https://github.com/YOUR_USERNAME/me-legal-jobs-tracker.git
cd me-legal-jobs-tracker
```

### 2. Copy all files

```
me-legal-jobs-tracker/
├── main.py
├── config.py
├── firms.py
├── requirements.txt
├── .env.example
├── .gitignore
├── scrapers/
│   ├── __init__.py
│   ├── base.py
│   ├── jobs.py
│   ├── job_boards.py
│   ├── recruiter.py
│   ├── press.py
│   ├── chambers.py
│   ├── rss.py
│   └── website.py
├── classifier/
│   ├── __init__.py
│   ├── department.py
│   └── taxonomy.py
├── database/
│   ├── __init__.py
│   └── db.py
├── analysis/
│   ├── __init__.py
│   └── signals.py
├── alerts/
│   ├── __init__.py
│   └── notifier.py
├── dashboard/
│   ├── __init__.py
│   └── generator.py
├── docs/
│   └── index.html
└── .github/
    └── workflows/
        └── tracker.yml
```

### 3. Add GitHub Secrets

**Repo → Settings → Secrets and variables → Actions**

| Secret Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Your bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Your chat/channel ID |

### 4. Enable GitHub Pages

**Repo → Settings → Pages → Source: Deploy from branch → Branch: `main` → Folder: `/docs`**

Dashboard will be live at: `https://YOUR_USERNAME.github.io/me-legal-jobs-tracker/`

### 5. Push and test

```bash
git add .
git commit -m "Initial commit — ME Legal Jobs Tracker"
git push origin main
```

Then: **Actions → Run workflow → firm: latham** to test a single firm.

---

## Local Development

```bash
# Copy and fill in credentials
cp .env.example .env

# Install dependencies
pip install -r requirements.txt

# List tracked firms
python main.py --list-firms

# Test single firm
python main.py --firm latham

# Test another
python main.py --firm white_case

# Regenerate dashboard only
python main.py --dashboard

# Send digest only
python main.py --digest

# Full run
python main.py
```

---

## Cron Schedule

| Time | Action |
|---|---|
| Daily 06:00 UTC (09:00 Dubai/GST) | Full collection — all 7 scrapers × 21 firms |
| Sunday 08:00 UTC | Weekly ranked digest via Telegram |
| On demand | Manual dispatch from Actions tab |

---

## Telegram Output

**Instant alert** (fires within minutes of new associate role found):
```
💼 New ME Legal Job Posting

🏛 Latham & Watkins LLP
📍 Location: Dubai
👤 Role: Senior Associate
⚡ Practice: Energy & Natural Resources
🔗 View Posting

🖥 Open Dashboard →
```

**Instant alert (recruiter)**:
```
🔍 New ME Legal Job Posting

🏛 White & Case LLP
📍 Location: Abu Dhabi
👤 Role: Associate
⚖️ Practice: Arbitration & Disputes
🔍 Via: Taylor Root
📝 [Taylor Root] Associate — International Arbitration, Abu Dhabi
🔗 View Posting
```

**Sunday digest**:
```
⚖️ ME Legal Jobs Tracker
Week ending 9 March 2026
🖥 Open Dashboard →
────────────────────────────────────
12 new job posting(s)  |  3 lateral hire signal(s)
5 firm-department alert(s)

1. 🏛 Latham & Watkins LLP
   ⚡ Energy & Natural Resources — 📍 Dubai
   Score: 24.5  |  4 signal(s)
   2× recruiter posting  1× job posting  1× press release
   🔍 [Kershaw Leonard] Senior Associate — Energy, Dubai
   💼 [Latham] Energy Finance Associate — Dubai
   📢 [The Lawyer MEA] Latham expands Dubai energy team

2. 🏛 White & Case LLP
   ⚖️ Arbitration & Disputes — 📍 Abu Dhabi
   Score: 18.2  |  3 signal(s)
   ...
────────────────────────────────────
💼 Latest Associate Openings
• Project Finance Associate — Dubai  📍Dubai  (via Michael Page)
• International Arbitration Associate — Abu Dhabi  📍Abu Dhabi
• Banking Associate — Riyadh  📍Riyadh  (via Kershaw Leonard)
...
```

---

## Adding Firms

Edit `firms.py` and add an entry to the `FIRMS` list:

```python
{
    "id":           "firm_id",
    "name":         "Full Firm Name LLP",
    "short":        "Short Name",
    "alt_names":    ["Alt Name 1", "Abbreviation"],
    "website":      "https://www.firm.com",
    "careers_url":  "https://www.firm.com/careers",
    "me_offices": {
        "Dubai":     "https://www.firm.com/offices/dubai",
        "Abu Dhabi": "https://www.firm.com/offices/abu-dhabi",
    },
    "news_url":     "https://www.firm.com/news",
    "linkedin_slug":"firm-linkedin-slug",
    "hq":           "New York",
    "founded":      1900,
    "amlaw_rank":   50,
},
```

## Adding Recruiters

Edit `firms.py` (`ME_LEGAL_RECRUITERS` list) or `scrapers/recruiter.py` (`RECRUITERS` list):

```python
{
    "id":   "my_recruiter",
    "name": "Recruiter Name",
    "base": "https://www.recruiter.com",
    "jobs_url": "https://www.recruiter.com/legal-jobs-me/",
    "search_params": {"location": "uae", "sector": "legal"},
    "card_selector": re.compile(r"job|listing|card", re.I),
},
```

## Tuning the Classifier

Edit `classifier/taxonomy.py` to add keywords/phrases per department.
Phrase matches (multi-word) receive a **2.5× boost** over single keywords.

## What Gets Tracked — and What Doesn't

✅ **Tracked:**
- Law associate / lawyer / attorney / counsel / solicitor / trainee roles
- Senior associate and mid-level associate roles
- Any role at a tracked US firm in a ME location (Dubai, Abu Dhabi, Qatar, etc.)
- Lateral partner moves to ME offices (press signal)
- Recruiter postings on behalf of tracked US firms

❌ **Filtered out:**
- Paralegal, legal secretary, office manager, marketing, IT support, billing
- In-house / compliance-only roles
- Roles not located in tracked ME geographies
- Non-US firms
