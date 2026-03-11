# Setup Guide — ME Legal Jobs Tracker

## Prerequisites

- Python 3.11+
- A GitHub account
- A Telegram account (for alerts)

---

## Step 1 — Telegram Bot Setup

1. Open Telegram, search for **@BotFather**
2. Send `/newbot` and follow prompts
3. Copy the **bot token** (format: `123456789:ABCdef...`)
4. Send `/start` to your bot, then send any message
5. Get your **chat ID**:
   ```
   https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   ```
   Look for `"chat": {"id": 123456789}` in the response

---

## Step 2 — GitHub Repository

```bash
# Create private repo
gh repo create me-legal-jobs-tracker --private --clone
cd me-legal-jobs-tracker

# Copy all project files into the repo root
# (see README.md for file structure)

git add .
git commit -m "Initial commit"
git push origin main
```

---

## Step 3 — GitHub Secrets

Go to **Repo → Settings → Secrets and variables → Actions → New repository secret**

| Secret Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | The token from Step 1 |
| `TELEGRAM_CHAT_ID` | Your chat ID from Step 1 |

---

## Step 4 — Enable GitHub Pages

1. Repo → **Settings → Pages**
2. Source: **Deploy from a branch**
3. Branch: **main**  |  Folder: **/docs**
4. Click **Save**

Your dashboard URL will be:  
`https://YOUR_USERNAME.github.io/me-legal-jobs-tracker/`

Set this as the `DASHBOARD_URL` in your GitHub Secret (optional) for clickable links in Telegram.

---

## Step 5 — First Run

Trigger manually to test:

1. **Actions → ME Legal Jobs Tracker → Run workflow**
2. Leave `firm` blank for full run, or enter `latham` to test one firm
3. Check **Artifacts** for `tracker-log-*` to see what was collected

---

## Step 6 — Local Testing

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/me-legal-jobs-tracker.git
cd me-legal-jobs-tracker

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up local credentials
cp .env.example .env
# Edit .env and fill in TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID

# List all tracked firms
python main.py --list-firms

# Test one firm (fast)
python main.py --firm latham

# Run everything
python main.py

# Rebuild dashboard without re-scraping
python main.py --dashboard
```

---

## Cron Schedule (GitHub Actions)

| Schedule | Time | Action |
|---|---|---|
| `0 6 * * *` | 06:00 UTC = 09:00 Dubai | Daily full collection |
| `0 8 * * 0` | 08:00 UTC Sunday | Weekly digest |

To change timing, edit `.github/workflows/tracker.yml`.

---

## Common Issues

### No signals found
- Many job boards block scraping. The tracker uses rotating user-agents and delays, but some sites may still block. Check `tracker.log` for HTTP errors.
- Try running `python main.py --firm latham` and inspect the log for individual scraper results.

### Telegram not sending
- Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set correctly in GitHub Secrets.
- Ensure you sent a message to your bot first (to initialise the chat).
- For channels, make sure the bot is an admin.

### GitHub Pages not updating
- The workflow commits to `docs/` and pushes. Ensure the workflow has `write` permissions (set in `tracker.yml` under `permissions`).
- Check **Actions** for any permission errors.

### Rate limiting
- Increase `MIN_DELAY_SECS` and `MAX_DELAY_SECS` in `.env` or GitHub Secrets.
- Reduce the number of firms per run using `--firm`.
