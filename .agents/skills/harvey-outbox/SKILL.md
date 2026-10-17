---
name: harvey-outbox
description: Outbox review and copilot queue management. Queries SQLite (data/harvey.db) for pending drafts, displays them alongside matched prospect signals and gate safety checks, and lets the user approve, edit, or reject drafts directly. Trigger with /harvey-outbox.
---

# Harvey Outbox Workflow (`/harvey-outbox`)

Use this workflow to review, edit, approve, or reject queued outbound emails with full signal transparency before anything is sent.

---

## Workflow Steps

### Step 1: Query Pending Review Items
Query the local SQLite database (`data/harvey.db`) for pending drafts:

```python
import sqlite3

conn = sqlite3.connect("data/harvey.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

query = """
SELECT o.id, o.step, o.kind, o.to_email, o.subject, o.body, o.status, o.send_at,
       p.first_name, p.last_name, p.title, p.company, p.personalization_notes, p.email_status,
       c.domain, c.tech_stack
FROM outbox o
LEFT JOIN prospects p ON o.prospect_id = p.id
LEFT JOIN companies c ON p.company_id = c.id
WHERE o.status = 'pending_review'
ORDER BY o.created_at ASC
LIMIT 20;
"""
rows = cursor.execute(query).fetchall()
```

Or quickly check via CLI:
```bash
harvey outbox
```

### Step 2: Display Each Draft with Grounded Signals
For each pending draft, present a clear, human-readable card:

```markdown
### [Outbox ID: {id}] Step {step} ({kind})
- **Recipient**: {first_name} {last_name} ({title}) at **{company}**
- **Email**: `{to_email}` (Verification: `{email_status}`)
- **Matched Signals & Notes**:
  - Personalization notes: {personalization_notes}
  - Tech stack: {tech_stack}
- **Subject**: `{subject}`
- **Body**:
> {body}

- **Pre-Send Gate Check**:
  - Words: {word_count} (Email 1 limit: 75 words)
  - Em dashes: {zero em dashes verified}
  - Deliverability: {verified / risky}
```

### Step 3: Interactive Decision (Approve, Edit, or Reject)

Present the user with clear options for each item or for the whole batch:

1. **Approve a single message**:
   ```bash
   harvey outbox --approve <ID>
   ```
2. **Approve all pending messages**:
   ```bash
   harvey outbox --approve-all
   ```
3. **Reject/kill a draft**:
   ```bash
   harvey outbox --reject <ID>
   ```
4. **Edit a draft**:
   If the user requests copy changes (e.g., shorter opener, different question), update the record in SQLite directly:
   ```python
   cursor.execute(
       "UPDATE outbox SET subject = ?, body = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
       (new_subject, new_body, item_id)
   )
   conn.commit()
   ```

### Step 4: Verify Outbox Schedule
Show the remaining queue and scheduled send times:
```bash
harvey outbox
```
Remind the user that approved emails are automatically sent by Harvey's heartbeat loop during business hours, honoring daily send limits and jitter delays.
