# Harvey — Autonomous AI Sales Agent

Harvey is an autonomous sales agent powered by Google Antigravity (`agy`) and Gemini. It finds prospects, writes cold emails, sends campaigns via native mail providers (Gmail, Microsoft 365, SMTP) or Instantly, handles replies, and books meetings — all on its own.

**You (Gemini / Antigravity agent) are the guide.** When someone opens this project in Antigravity, your job is to help them understand what Harvey is, get it configured, and start closing deals. Be conversational, not robotic. Explain things simply. Ask one thing at a time.

---

## When Someone First Opens This Project

Start by checking what state things are in. Don't dump a wall of setup steps — figure out where they are and guide them from there.

### Quick health check (do this silently):
1. Does `.venv/` exist? → If not, they need install (`python -m venv .venv` with Python 3.11+)
2. Is `harvey` importable? → If not, dependencies need installing (`pip install -e .`)
3. Does `.env` exist with real values? → If not, they need API keys
4. Does `harvey.yaml` (or `harvey.local.yaml`) have real values (not "Your Company")? → If not, they need product training
5. Does `data/harvey.db` exist? → If not, Harvey hasn't run yet

### Then introduce yourself based on what you find:

**If nothing is set up:**
> "This is Harvey — an autonomous AI sales agent. It finds people who match your ideal customer, writes personalized cold emails, sends them, and handles replies automatically. It can run on your Google Antigravity (`agy`) / Gemini environment so there's no extra model API cost.
>
> Let me help you get it set up. It takes about 5 minutes. First, let me install the dependencies..."

**If partially set up:**
> "Looks like Harvey is partially configured. [specific thing] is done but [specific thing] still needs setting up. Want me to pick up where you left off?"

**If fully set up:**
> "Harvey is configured and ready to go. Want me to start it, show you the dashboard, or explain how it works?"

---

## Explaining Harvey to Users

People will ask "how does this work?" — explain it simply:

- **"What does Harvey do?"** → It's like having a tireless sales assistant. Every 15 minutes it wakes up, checks what needs doing, does it, and goes back to sleep. It finds prospects, writes emails, sends campaigns, and responds to replies.

- **"How does it find people?"** → It searches the web (DuckDuckGo, Bing, Google, Serper, DataForSEO, OpenStreetMap) for companies matching your target profile, visits their websites, and finds team members. For emails, it learns each company's address pattern (from their site, or a free Hunter domain lookup) and verifies a single candidate through a free verification tier — every address is tagged verified / catch-all / guess, and only deliverable ones get sent. No expensive tools needed.

- **"How does it write emails?"** → It uses proven cold email frameworks (like AIDA and PAS) with strict rules — short, personal, no AI-sounding language. Each email is tailored to the specific person and their company.

- **"Is it safe?"** → Yes. It runs locally on your machine, has daily usage limits, quiet hours, and send limits built in. It has a deterministic pre-send gate that catches banned spam phrases, HTML tags, unrendered merge tags, and invalid email statuses. It can't delete files, access your bank account, or do anything outside its sales workflow. Everything it does is logged in a local SQLite database you can inspect anytime.

- **"What does it cost?"** → Just your existing Google Antigravity / Gemini or Claude/ChatGPT subscription. The native email channels (Gmail/Workspace, Microsoft 365, SMTP) require no sequencer subscription. If you choose Instantly, their starter plan works. Verification has generous free tiers (Reoon: 600/mo, ZeroBounce: 100/mo, Hunter: 50/mo).

- **"Can it use Antigravity (`agy`) / Gemini?"** → Yes! Harvey supports Antigravity (`agy`) and Gemini subscriptions natively, as well as Claude Code and Codex (ChatGPT). When using Antigravity, Harvey leverages your `agy` environment and quota while keeping prompt execution tool-isolated and secure. Claude and Codex remain available alternatives.

- **"What's the dashboard?"** → Run `harvey dashboard` to see a local web UI at http://localhost:5555. It opens on **Today** — anything waiting on a decision, then the pipeline. Tabs for Signals, Companies, Contacts, Campaigns, Outbox, Conversations, Activity, Usage, Settings.

- **"What are signals?"** → Signals are the facts Harvey collects about a business: who its current agency is, whether it's running ads, whether it has online booking, how it ranks. **Harvey proposes; you confirm.** Nothing is collected until the user says yes on the Signals tab (or `harvey signals --confirm ...`). That keeps spend intentional and makes every prospect list explainable — a cohort is a query over signals a human chose, not a black box.

---

## Setup Flow

Walk through these steps conversationally. Ask one thing at a time. Don't overwhelm.

### Step 1: Install Dependencies

Ensure Python 3.11+ is used. Always run inside the project virtual environment:

```bash
# On Linux / macOS:
python3 -m venv .venv && source .venv/bin/activate && pip install -e .

# On Windows (PowerShell):
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
```

Then install the browser for LinkedIn prospecting:
```bash
python -m playwright install chromium
```

### Step 2: API Keys (`.env`)

Harvey needs an **email provider** (to send + read replies) and, strongly recommended, an **email verifier**. Pick one provider:

```ini
# --- Email provider: choose ONE, set channels.email.provider to match ---
GMAIL_CLIENT_ID=            # Recommended: Gmail/Workspace. Then run 'harvey gmail auth'
GMAIL_CLIENT_SECRET=
# --- or Microsoft 365 / Outlook Graph API ---
M365_CLIENT_ID=  M365_TENANT_ID=   # Then run 'harvey microsoft auth'
# --- or SMTP+IMAP (AgentMail, Fastmail, Workspace app password) ---
SMTP_HOST=  SMTP_PORT=587  SMTP_USERNAME=  SMTP_PASSWORD=
IMAP_HOST=  IMAP_PORT=993
# --- or legacy Instantly ---
INSTANTLY_API_KEY=

# --- Email verification (add at least one; else emails stay 'guess') ---
REOON_API_KEY=              # 600 free/mo — best free tier
ZEROBOUNCE_API_KEY=         # 100 free/mo — best for M365/Workspace catch-alls
HUNTER_API_KEY=             # 50 free/mo + pattern lookup

# --- Discovery (optional — the free OpenStreetMap source needs no key) ---
DATAFORSEO_LOGIN=  DATAFORSEO_PASSWORD=   # cheapest local-business + SERP data
DATAFORSEO_SANDBOX=                       # any value routes to the free sandbox

# --- Optional ---
LINKEDIN_EMAIL=  LINKEDIN_PASSWORD=   # LinkedIn prospecting
CLOUDFLARE_ACCOUNT_ID=  CLOUDFLARE_API_TOKEN=   # deep JS crawling for training
SERPER_API_KEY=            # web search + discovery (2,500 free, then a $50 prepaid pack)
```

**Recommended provider — Gmail or Microsoft 365:** for <50 cold emails/day, a real Google Workspace or M365 mailbox on a *dedicated secondary domain* (never your main domain) is the most deliverable and cost-effective option.
- For Gmail: set `channels.email.provider: gmail` in `harvey.yaml`, put OAuth credentials in `.env`, run `harvey gmail auth`.
- For M365: set `channels.email.provider: microsoft`, run `harvey microsoft auth`.
- For SMTP: set `channels.email.provider: smtp`.
- For Instantly: set `channels.email.provider: instantly` and set `INSTANTLY_API_KEY`.

**Email verification matters:** Harvey learns each company's email *pattern* and verifies ONE candidate rather than guessing. Without a verifier key, found emails are marked `guess` and are **never sent**.

**Approval by default:** with a native provider, every outgoing email waits in the **Outbox** for your approval (dashboard Outbox tab, or `harvey outbox`). Once you trust the output, set `channels.email.require_approval: false` in `harvey.yaml` for full autopilot.

### Step 3: Product Training

Harvey needs to know what it is selling.

**Option A — Train from a website URL (recommended):**
```bash
harvey train https://their-website.com
```
This generates: `harvey.yaml` (or updates it), `skills/product_knowledge.md`, and `skills/competitive_intel.md`.

**Option B — Manual configuration:**
Guide the user through these questions and build `harvey.yaml` and `skills/product_knowledge.md`:
- Company name and persona identity
- What you sell (product/service name, one-line value prop)
- Pricing structure
- Top 3-5 key benefits
- Target ICP (industries, titles, company size, geography)
- Primary offer and low-commitment entry offer (trial, audit, consultation)
- Meeting scheduling details (booking method, link, duration, host)

### Step 4: Confirm Signals

Harvey ships a catalog of ~19 signals it knows how to collect, all **proposed** and none active. Nothing is prospected against until the user confirms them.

Send them to `harvey dashboard` → **Signals**, or manage via CLI:

```bash
harvey signals                      # review the catalog
harvey signals --confirm free       # turn on everything that costs nothing
harvey signals --confirm SERP_RANK  # confirm specific signal
```

Most signals are free (they inspect pages a business already publishes). Only `SERP_RANK` and `EMAIL_STATUS` consume credits.

### Step 5: Find Businesses

Discovery estimates spend before executing:

```bash
harvey discover --providers                        # menu with real pricing
harvey discover --estimate                         # projected spend, then exits
harvey discover                                    # free OpenStreetMap source
harvey discover --provider dataforseo_listings --max-spend 2.00
```

| Source | Cost | Free tier | Best for |
|---|---|---|---|
| **OpenStreetMap** (default) | free | unlimited | Quick start with zero account creation. |
| **DataForSEO Listings** | $0.372 / 1k businesses | $1 credit | Local trades, clinics, contractors, businesses without websites. |
| **DataForSEO SERP** | $0.0018 / search (depth 30) | $1 credit + sandbox | Organic search ranking signals (sweet spot: pos 11-30). |
| **Serper** | ~$0.30 - $1.00 / 1k | 2,500 free | Reliable paid web search discovery. |

### Step 6: Behavior Settings

Configure in `harvey.yaml` under `usage:`:
- `max_daily_claude_percent`: 80 (quota utilization ceiling)
- `heartbeat_interval_minutes`: 15 (check frequency)
- `quiet_hours`: 22:00-07:00 in user's timezone
- `max_daily_sends`: 50 (daily outbound ceiling)

### Step 7: Start Harvey

```bash
harvey run
```
Or open the dashboard:
```bash
harvey dashboard
```

---

## After Setup — Ongoing Help

Common operational tasks:
- **"Show me what Harvey has done"** → Run `harvey status` or open `harvey dashboard`.
- **"The emails aren't good"** → Edit `skills/email_frameworks.md` and `prompts/writer.md`.
- **"Harvey isn't finding the right people"** → Adjust `icp:` in `harvey.yaml`.
- **"I want to change what Harvey says"** → Skills are in `skills/`, prompts in `prompts/`. Both are plain markdown files.
- **"Train Harvey on a different product"** → `harvey train <new-url>`.
- **"How do I see the database?"** → SQLite database at `data/harvey.db`.
- **"Export prospect list"** → `harvey export` (verified/risky only) or `harvey export --all` for full list.

---

## How Harvey Works (Technical Reference)

### Architecture
- **Heartbeat loop** (`main.py`): Cycle → check quiet hours → check quota budget → decide next action → execute agents → stage/drain outbox → sleep.
- **Brain** (`brain.py`): Orchestrates LLM calls across providers (`antigravity`, `claude`, `codex`). Enforces zero-tool execution boundary, strict timeout, exponential backoff retries, and token/call accounting.
- **State** (`state.py`): SQLite database at `data/harvey.db` managing prospects, companies, campaigns, outbox items, conversations, observations, and usage events.
- **Usage tracking** (`usage.py`, `integrations/quota.py`): Tracks per-call attribution (agent, task, model, tokens) for Harvey's own calls and reads live subscription quota gauges.
- **Pre-send Gate** (`gate.py`): Deterministic non-LLM safety filter checking banned spam words, AI markers, max words, single link constraint, unrendered merge variables, plain text formatting, and deliverability status.
- **Signals & Cohorts** (`signals.py`, `state.py`): Observed business facts stored in `observations`. Only `confirmed` signals are used.
- **Dashboard** (`dashboard.py` + `harvey/web/`): Fast local web UI served via FastAPI with pure HTML/CSS/JS (no Node build step required).
- **Discovery** (`collectors/discover.py`): Modular discovery providers (`osm`, `dataforseo_listings`, `dataforseo_serp`, `serper`) with cost estimation and hard spending caps.

### Sub-Agents
- **Scout** (`agents/scout.py`): Searches web sources, detects tech stack (Shopify, HubSpot, etc.), scrapes careers pages for hiring signals, resolves email patterns, and verifies deliverability. Claude/Gemini only scores/personalizes.
- **Writer** (`agents/writer.py`): Generates personalized sequences. With native providers, Email 1 is written uniquely per prospect from grounded company facts.
- **Sender** (`agents/sender.py`): Stages sequences into the outbox (`pending_review` by default), enforces daily limits, paces sends with jitter, verifies stop-on-reply, and sends via chosen provider.
- **Handler** (`agents/handler.py`): Polls for replies, dedups, classifies intent, updates conversation stages, handles bounce detection and auto-pause tripwires.
- **Analyst** (`agents/analyst.py`): Computes pipeline statistics and saves insights to `data/analytics.json`.

### Conversation Stages
`initial_outreach → engaged → qualifying → presenting → negotiating → closing → closed_won / closed_lost`

### Priority Order
`handle_replies > send_campaign > write_campaign > prospect > idle (run analyst)`

### Key Commands
```bash
# Environment & Setup
source .venv/bin/activate       # Unix/macOS: activate venv
.venv\Scripts\Activate.ps1      # Windows: activate venv
harvey install                  # Install dependencies & Playwright browsers
harvey setup                    # Interactive setup wizard
harvey train <url>              # Learn product positioning from a website

# Runtime & Monitoring
harvey run                      # Run autonomous heartbeat loop
harvey dashboard                # Web UI at http://localhost:5555
harvey status                   # Pipeline summary (--check for brain readiness)
harvey usage                    # Provider quota & call ledger breakdown

# Email & Outbox Management
harvey outbox                   # Review queued outbound emails
harvey outbox --approve <id>    # Approve single message
harvey outbox --approve-all     # Approve all pending outbound messages
harvey outbox --reject <id>     # Reject queued message
harvey sending pause|resume     # Global emergency kill switch

# Provider Auth & Testing
harvey gmail auth|test          # Gmail OAuth setup & connection test
harvey microsoft auth|test      # Microsoft 365 OAuth & connection test

# Prospecting & Signals
harvey signals                  # Review signal catalog (--confirm free/all)
harvey discover                 # Discover businesses (--providers, --estimate)
harvey profile                  # Free website profiling
harvey export                   # Export sequencer-ready CSV (prospects.csv)
```

### Common Issues
- **Command not found: harvey**: Ensure virtual environment is activated (`.venv`).
- **Python version error**: Harvey requires Python 3.11+. Re-create `.venv` with a Python 3.11+ binary.
- **Brain provider errors**: Verify active login session or credentials for your configured provider in `harvey.yaml`.
- **Emails stuck in Outbox**: Harvey operates in Copilot mode by default (`channels.email.require_approval: true`). Review and approve items in `harvey outbox` or the web dashboard.
- **Bounces or kill switch triggered**: If bounce rate exceeds threshold (`max_bounce_rate`), sending pauses automatically. Inspect bounced contacts, resolve verification issues, and run `harvey sending resume`.
