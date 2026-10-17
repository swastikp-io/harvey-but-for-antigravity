---
name: harvey-setup
description: Interactive setup wizard for Harvey. Checks .venv and Python version, guides .env API key configuration, runs product training (harvey train <url>), and confirms free signals (harvey signals --confirm free). Trigger with /harvey-setup.
---

# Harvey Setup Wizard (`/harvey-setup`)

Use this workflow to guide the user through a clean, frictionless setup of Harvey in Google Antigravity.

---

## Workflow Steps

### Step 1: Python Virtual Environment & Installation Check
Silently or explicitly verify the environment:
1. Check if `.venv/` exists:
   - On Windows: `.venv\Scripts\python.exe --version`
   - On Linux/macOS: `.venv/bin/python --version`
2. Ensure Python version is 3.11+.
3. Check if package dependencies are installed by running:
   ```bash
   .venv\Scripts\python.exe -c "import harvey; print(harvey.__file__)"
   ```
4. If missing, guide user or run:
   ```bash
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -e .
   python -m playwright install chromium
   ```

### Step 2: Environment Variables (`.env`) Audit
Check whether `.env` exists in the repository root and inspect configured keys:
- **Email Provider (Required - Choose 1)**:
  - `GMAIL_CLIENT_ID` and `GMAIL_CLIENT_SECRET` (Run `harvey gmail auth` afterwards)
  - OR `M365_CLIENT_ID` and `M365_TENANT_ID` (Run `harvey microsoft auth` afterwards)
  - OR `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`
  - OR `INSTANTLY_API_KEY`
- **Email Verifier (Strongly Recommended)**:
  - `REOON_API_KEY` (600 free/mo)
  - `ZEROBOUNCE_API_KEY` (100 free/mo)
  - `HUNTER_API_KEY` (50 free/mo)
  *(Remind user: Without a verifier key, found emails remain marked 'guess' and cannot be sent!)*
- **Model Provider**:
  - Check `harvey.yaml`: confirm `brain.provider` is set to `antigravity`, `claude`, or `codex`.

### Step 3: Product Training
Ask the user for their product or company website:
1. Ask: *"What is the website URL of the product or company you want Harvey to sell?"*
2. Once provided, run the training command:
   ```bash
   harvey train <URL>
   ```
3. Verify that training generated:
   - Updated `harvey.yaml`
   - `skills/product_knowledge.md`
   - `skills/competitive_intel.md`

### Step 4: Confirm Signals
Explain Harvey's intentional signal philosophy:
> *"Harvey never burns credits or prospects blindly. It proposes signals, and you choose what to collect. Most signals are completely free (inspecting public website data)."*

Run:
```bash
harvey signals --confirm free
```
Show the user the confirmed signals list:
```bash
harvey signals
```

### Step 5: Verify Connectivity & Readiness
Run a diagnostic health check:
```bash
harvey status --check
```
If using Gmail or M365, verify authentication:
- Gmail: `harvey gmail test`
- Microsoft: `harvey microsoft test`

Congratulate the user and offer next steps:
- Run `/harvey-discover` to discover prospective accounts.
- Run `harvey dashboard` to view the web UI at `http://localhost:5555`.
