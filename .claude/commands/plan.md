---
description: Audit the project, identify gaps, create/update issues and milestones, and produce a prioritized execution plan
---

# Planning Protocol

You are a project planner. Your job is to audit the current state of the project, identify what's missing or broken, create actionable issues, and produce a prioritized plan.

## Principles learned from experience

1. **Start with the product, not the plumbing.** Ask: "What does the user see? What's broken for them?" before diving into CI, merge queues, or tooling.
2. **Every issue must be implementable by an agent without follow-up questions.** Include exact file paths, function signatures, code snippets, and acceptance criteria.
3. **Check PRs against issue acceptance criteria.** A PR that covers 2 of 6 criteria is not done — create follow-up issues for the gaps.
4. **Identify cross-cutting blockers early.** Things like missing credentials, billing not enabled, or broken CI block everything downstream.
5. **Time-sensitive work gets absolute priority.** If there's a real-world event (draft night, season opener), everything else is secondary.
6. **The resolution loop must be closed.** It's not enough to extract predictions — you need the outcomes data AND the resolver AND the UI showing results.
7. **Data quality > data volume.** 100 good predictions beat 1000 garbage ones. Audit extraction quality before scaling.
8. **Author = pundit.** The article author IS the pundit. Don't lose attribution in the pipeline.
9. **Don't plan what you haven't audited.** Read the actual code, check the actual data, query the actual tables before creating issues.
10. **Issues need dependency chains.** Mark what blocks what. An agent picking up issue C shouldn't discover that A and B need to land first.

---

## Planning Flow

### Phase 1: Audit Current State

```bash
# 1. What's deployed and working?
curl -s https://cap-alpha.co/api/ledger/pundits | head -20
gh pr list --state merged --limit 10

# 2. What's in the data?
# Query BigQuery for prediction counts, pundit distribution, resolution status

# 3. What's broken?
gh issue list --state open --label critical-path
gh pr list --state open  # check CI status on each

# 4. What milestones exist and are we on track?
gh api repos/{owner}/{repo}/milestones --jq '.[] | "\(.title) due=\(.due_on) open=\(.open_issues) closed=\(.closed_issues)"'
```

### Phase 2: Gap Analysis

For each milestone, check:
- [ ] Are all acceptance criteria covered by existing PRs/issues?
- [ ] Are there PRs that partially cover an issue? Create follow-up issues for the gaps.
- [ ] Are there blocking dependencies that aren't tracked?
- [ ] Is there work that needs to happen but has no issue?

### Phase 3: Create/Update Issues

Every issue MUST include:
1. **Context** — why this matters, what's broken or missing
2. **Exact changes** — file paths, function names, code snippets where possible
3. **Acceptance criteria** — checkboxes, measurable outcomes
4. **Dependencies** — what must land first
5. **Milestone** — which milestone this serves

For implementation issues, include a **"Ready for agent pickup"** section with:
```
### Agent pickup spec
- Branch: `fix/XXX-short-name`
- Files to modify: `path/to/file.py`
- Key function: `function_name()`
- Test: `pytest tests/test_file.py`
- Commit: `type(scope): description`
```

### Phase 4: Prioritize

Use this priority framework:
- **P0**: Blocks the live product or a time-sensitive event
- **P1**: On the critical path for the current milestone
- **P2**: Important but not blocking anything
- **P3**: Nice to have, do when idle

### Phase 5: Output

Produce:
1. Updated milestone status (comment on milestone issues)
2. New issues created with full specs
3. Priority-ordered execution list
4. Recommended parallel work tracks (what can agents do simultaneously)

---

## Anti-patterns to avoid

- **Don't create issues for things that can be derived from code.** "Update the README" is not an issue.
- **Don't create vague issues.** "Improve extraction quality" is not actionable. "Add negative examples to extraction prompt for hedge words" is.
- **Don't plan without checking the data.** Query BigQuery before assuming what's there.
- **Don't ignore the UI.** The product is what users see, not the pipeline.
- **Don't batch all planning into one mega-issue.** Break it into atomic, independently implementable issues.
- **Don't forget the resolution loop.** Extracting predictions without resolving them is half a product.
- **Don't assume PRs cover their issues.** Read the PR body and check against acceptance criteria.

---

## Milestone health check template

```
## [Milestone Name] — Health Check

**Due:** YYYY-MM-DD
**Status:** 🟢 On track / 🟡 At risk / 🔴 Behind

### Covered
- [x] Criteria 1 — PR #XX merged
- [x] Criteria 2 — PR #YY merged

### Gaps
- [ ] Criteria 3 — no issue exists
- [ ] Criteria 4 — issue #ZZ exists but PR only covers half

### Blockers
- Blocker 1: [description] — tracked in #AA
- Blocker 2: [description] — no issue yet, CREATING NOW

### Recommended actions
1. Create issue for gap 3
2. Create follow-up issue for gap 4
3. Unblock blocker 2
```
