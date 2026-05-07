# Cap Alpha — Correction & Retraction Policy

**Last Updated:** May 4, 2026  
**Public URL:** https://cap-alpha.co/legal/corrections

---

## Summary

Cap Alpha uses a cryptographic ledger. Wrong resolutions are **appended with a correction entry**, never overwritten. The original wrong entry is preserved permanently so the full audit trail is intact.

---

## Correction Entry Format (Ledger)

When a correction is applied, the pipeline appends a new ledger entry:

```json
{
  "entry_type": "correction",
  "original_claim_id": "<claim_id>",
  "original_outcome": "INCORRECT",
  "corrected_outcome": "CORRECT",
  "reason": "Cited source was misidentified; correct source confirms CORRECT",
  "corrected_by": "admin@cap-alpha.co",
  "correction_timestamp": "2026-05-04T18:00:00Z"
}
```

The original entry is NOT modified. Its hash chain is preserved.

---

## Internal Runbook — Processing a Correction

### 1. Receive and triage

- Source: `corrections@cap-alpha.co`
- Acknowledge within 24 hours (template: `docs/templates/correction-ack.md` — TBD)
- Log the claim in a GitHub issue tagged `correction`

### 2. Investigate

- Pull the claim from BigQuery: `pipeline/src/cryptographic_ledger.py`
- Check the source document (transcript, article, tweet)
- Cross-reference with at least one independent source

### 3. Decide

| Outcome | Action |
|---------|--------|
| Clear factual error | Apply correction immediately |
| Ambiguous interpretation | Mark VOID with documented reasoning |
| Claim upheld (no error) | Reply with reasoning, close issue |

### 4. Apply correction (if warranted)

```bash
# From the main checkout (not a worktree — this is an ops script)
source .venv/bin/activate
python pipeline/scripts/apply_correction.py \
  --claim-id <claim_id> \
  --corrected-outcome CORRECT \
  --reason "Brief explanation here" \
  --operator "your@email.com"
```

> **Note:** `pipeline/scripts/apply_correction.py` — TODO: create this script (tracks issue #372)

### 5. Notify affected users

- Email users who bookmarked the prediction or follow the pundit
- Template: `docs/templates/correction-notification.md` — TBD
- SLA: within 24 hours of correction being applied

### 6. Close the issue

- Update the GitHub issue with the correction entry hash
- Tag it `correction-applied`

---

## Escalation

If a correction request involves a legal claim (defamation, copyright), escalate to `legal@cap-alpha.co` before taking any action.

---

## SLA

| Step | Target |
|------|--------|
| Acknowledgment | 24 hours |
| Decision (clear factual errors) | 48 hours |
| Decision (contested interpretations) | 7 calendar days |
| Ledger update | Same business day as decision |
| User notification | 24 hours after ledger update |
| Appeal resolution | 5 business days |
