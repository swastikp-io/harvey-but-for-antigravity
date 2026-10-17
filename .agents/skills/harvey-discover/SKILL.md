---
name: harvey-discover
description: Discover prospective businesses matching ICP. Runs cost estimation before spending (harvey discover --estimate), confirms with user, executes discovery (harvey discover), and profiles websites (harvey profile) for tech stack, team members, and signals. Trigger with /harvey-discover.
---

# Harvey Discover Workflow (`/harvey-discover`)

Use this workflow to find targeted accounts without blind spending or scraping waste.

---

## Workflow Steps

### Step 1: Review Discovery Providers
Display available discovery sources and their cost structures:
```bash
harvey discover --providers
```

| Source | Cost | Free tier | Best for |
|---|---|---|---|
| **OpenStreetMap (`osm`)** | $0.00 (Free) | Unlimited | Quick start with zero account creation or credentials. |
| **DataForSEO Listings (`dataforseo_listings`)** | $0.372 / 1k businesses | $1 credit | Local trades, clinics, contractors, businesses without websites. |
| **DataForSEO SERP (`dataforseo_serp`)** | $0.0018 / search (depth 30) | $1 credit + sandbox | Organic search ranking signals (sweet spot: pos 11-30). |
| **Serper (`serper`)** | ~$0.30 - $1.00 / 1k | 2,500 free | Reliable paid web search discovery. |

### Step 2: Run Cost Estimate First
Always run an estimate before triggering any paid provider to project the exact spend:
```bash
harvey discover --provider osm --estimate
# or for DataForSEO:
harvey discover --provider dataforseo_listings --estimate
```

### Step 3: Confirm with User
Present the estimated spend, number of queries, and target locations/industries to the user.
- If using `osm` (OpenStreetMap), inform the user that cost is **$0.00**.
- If using a paid provider, request explicit confirmation of the hard spend cap (`--max-spend <dollars>`).

### Step 4: Execute Discovery
Run the discovery command with the chosen provider and spend cap:
```bash
# Free default:
harvey discover --provider osm

# Or with custom city and spend cap:
harvey discover --provider dataforseo_listings --max-spend 1.50 --city "Austin, TX;Dallas, TX"
```

### Step 5: Profile Discovered Websites
Harvey separates discovery (finding the business) from profiling (reading the website).
Profiling is 100% free and consumes zero LLM quota:
```bash
harvey profile --limit 200
```
During profiling, Harvey:
1. Crawls homepage, about, team, and contact pages.
2. Identifies tech stacks (CMS, analytics, live chat, forms).
3. Detects team members and leadership roles.
4. Identifies footer agency credits (confidence >= 0.75).
5. Emits observations for all user-confirmed signals.

### Step 6: Report Discovered Pipeline
Summarize findings:
- Total new companies added to SQLite (`data/harvey.db`).
- Number of websites profiled and contacts discovered.
- Key signals detected (hiring, tech stack, agency credits).
- Suggest running `/harvey-outbox` to review the generated personalized outreach drafts.
