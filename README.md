# 🤖 JobHunter AI — Autonomous Multi-Agent Job Search System

An always-on AI agent that searches the internet for jobs, finds recruiters, drafts personalized outreach emails, and queues applications for your review. Runs 24/7 on GitHub Actions — completely free.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR AGENT                        │
│              (Coordinates all sub-agents)                    │
└──────┬──────┬──────┬──────┬──────┬──────────────────────────┘
       │      │      │      │      │
       ▼      ▼      ▼      ▼      ▼
   ┌──────┐┌──────┐┌──────┐┌──────┐┌──────┐
   │ JOB  ││SCORE ││QUEUE ││FIND  ││DRAFT │
   │SEARCH││ AI   ││ APPS ││RECRU-││EMAILS│
   │AGENT ││AGENT ││AGENT ││ITERS ││AGENT │
   └──┬───┘└──┬───┘└──┬───┘└──┬───┘└──┬───┘
      │       │       │       │       │
      ▼       ▼       ▼       ▼       ▼
  ┌───────────────────────────────────────┐
  │          📧 EMAIL NOTIFIER            │
  │    Sends digest to your inbox         │
  └───────────────────────────────────────┘

Data Sources:
  • Google Jobs (via Serper API)
  • Greenhouse ATS (public API)
  • Lever ATS (public API)
  • Ashby ATS (public API)
  • YC Work at a Startup (Algolia API)
  • Direct career page search
```

---

## ⚡ Quick Start (5 minutes)

### 1. Fork & Clone

```bash
# Fork this repo on GitHub, then:
git clone https://github.com/YOUR_USERNAME/job-hunter-ai.git
cd job-hunter-ai
```

### 2. Configure Your Profile

Edit `config/profile.yaml` with your details:
- Name, email, phone, location
- Target roles (AI Engineer, Software Engineer, etc.)
- Skills, experience, education
- Projects (used in recruiter outreach emails)
- Job preferences (salary, remote, locations)

### 3. Add Your Startups List

Edit `config/startups.yaml` with companies you want to track:
```yaml
startups:
  - name: "Cool AI Startup"
    domain: "coolai.com"
    careers_url: "https://coolai.com/careers"
    ats: "greenhouse"  # greenhouse, lever, ashby
    stage: "seed"
    focus: "What they do"
```

### 4. Set Up API Keys

You need these API keys (add as GitHub Repository Secrets):

| Secret Name | Required | How to Get | Cost |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ Yes | [console.anthropic.com](https://console.anthropic.com/) | ~$0.50/day |
| `SERPER_API_KEY` | ⭐ Recommended | [serper.dev](https://serper.dev/) | Free (2500/mo) |
| `SMTP_EMAIL` | ⭐ Recommended | Your Gmail address | Free |
| `SMTP_PASSWORD` | ⭐ Recommended | [Gmail App Password](https://myaccount.google.com/apppasswords) | Free |
| `JH_EMAIL` | Optional | Override notification email | — |

#### Setting up Gmail App Password:
1. Enable 2-Factor Authentication on your Google Account
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Create a new App Password for "Mail"
4. Use the 16-character password as `SMTP_PASSWORD`

### 5. Add Secrets to GitHub

Go to your repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add each secret from the table above.

### 6. Enable GitHub Actions

Go to your repo → **Actions** tab → Enable workflows.

**That's it!** The agent will start running every 15 minutes automatically.

### 7. Test Manually

Go to **Actions** → **🤖 JobHunter AI Agent** → **Run workflow** → Click **Run workflow**

---

## 📁 Project Structure

```
job-hunter-ai/
├── .github/workflows/
│   └── job-agent.yml          # GitHub Actions (runs every 15 min)
├── agents/
│   ├── orchestrator.py        # Main coordinator
│   ├── job_searcher.py        # Multi-source job search
│   ├── recruiter_finder.py    # LinkedIn recruiter discovery
│   ├── email_drafter.py       # AI-powered outreach emails
│   ├── application_manager.py # Application queue & pre-fill
│   └── notifier.py            # Email digest notifications
├── config/
│   ├── profile.yaml           # YOUR profile & preferences
│   └── startups.yaml          # Startups to track
├── data/                      # Auto-generated, persisted across runs
│   ├── seen_jobs.json         # Dedup: already-seen job IDs
│   ├── job_queue.json         # All discovered jobs
│   ├── application_queue.json # Queued applications for review
│   ├── recruiters.json        # Found recruiters & insights
│   ├── recruiter_drafts.json  # Draft outreach emails
│   ├── cycle_log.json         # Run history
│   └── last_digest.json       # Last email digest (fallback)
├── main.py                    # Entry point
├── requirements.txt
├── .env.example
└── README.md
```

---

## 🔄 How It Works (Per Cycle)

Every 15 minutes, the agent runs this pipeline:

1. **🔍 Job Search** — Searches 6+ sources in parallel for new postings matching your target roles
2. **🧠 AI Scoring** — Claude rates each job 0-100 based on relevance to your profile
3. **📝 Application Queue** — Jobs scoring above threshold are queued with pre-filled application data
4. **👤 Recruiter Discovery** — Finds hiring managers and recruiters at top companies via Google/LinkedIn
5. **✉️ Email Drafting** — Generates personalized outreach emails referencing your projects
6. **📧 Notification** — Sends you a beautifully formatted HTML email digest

---

## 📧 Email Notifications

You'll receive emails like:

```
🔥 JobHunter AI — 12 new jobs found!
Top: AI Engineer at Cognition AI

━━━ NEW JOB MATCHES ━━━
[95%] 🔥 AI Engineer — Cognition AI (SF, CA)
[88%] 🔥 ML Platform Engineer — Modal (Remote)
[82%] ⭐ Software Engineer, AI — Vercel (Remote)
...

━━━ OUTREACH DRAFTS READY ━━━
✉️ Jane Smith — Engineering Manager at Cognition AI
✉️ Bob Chen — Technical Recruiter at Modal
...
```

---

## 📋 Application Queue

The agent pre-fills these fields from your profile:
- ✅ Full name, email, phone, location
- ✅ LinkedIn, GitHub, portfolio URLs
- ✅ Resume link
- ✅ Years of experience
- ✅ Education details
- ✅ Skills list
- ✅ Work authorization
- ✅ Salary expectation

**You still need to fill:**
- Cover letter (optional)
- "Why this company?" responses
- Custom application questions
- Any company-specific fields

---

## ⚙️ Configuration Tips

### Adjusting Search Frequency

Edit `.github/workflows/job-agent.yml`:
```yaml
schedule:
  - cron: "*/15 * * * *"  # Every 15 minutes
  # - cron: "0 * * * *"   # Every hour
  # - cron: "0 */6 * * *" # Every 6 hours
```

> ⚠️ GitHub Actions free tier: 2000 minutes/month. At 15-min intervals, each run ~2-3min = ~288 runs/day = ~864 min/month. Well within limits.

### Adjusting Relevance Threshold

In `config/profile.yaml`:
```yaml
search:
  min_relevance_score: 60  # Lower = more jobs, higher = more selective
```

### Adding More Startups

Just add entries to `config/startups.yaml` and push. The agent picks them up next cycle.

---

## 🛠️ Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your API keys

# Run locally
python main.py
```

---

## 💰 Cost Estimate

| Service | Usage | Cost |
|---|---|---|
| GitHub Actions | ~864 min/month | **Free** (2000 min limit) |
| Anthropic API | ~100 calls/day | **~$0.30-0.50/day** |
| Serper API | ~200 searches/day | **Free** (2500/mo) |
| Gmail SMTP | ~96 emails/day | **Free** |
| **Total** | | **~$10-15/month** |

---

## 🚨 Troubleshooting

**No emails received?**
- Check GitHub Actions logs for errors
- Verify SMTP_EMAIL and SMTP_PASSWORD secrets
- Check spam folder
- Ensure Gmail App Password (not regular password)

**No jobs found?**
- Broaden target_roles in profile.yaml
- Lower min_relevance_score
- Add more startups to track
- Check if SERPER_API_KEY is set (needed for Google search)

**Rate limited?**
- Increase cron interval
- Reduce number of target roles
- Reduce number of tracked startups

---

## 📄 License

MIT — Use freely, modify as needed. Good luck with the job search! 🚀
