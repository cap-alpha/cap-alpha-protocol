#!/usr/bin/env python3
"""
AC Checklist Gate — fails if a closing PR references issues with unchecked ACs.

Called by .github/workflows/ac_checklist_gate.yml.

Escape hatches:
  - Issue has label 'ac-waiver' → skipped entirely.
  - Unchecked item is crossed out (~~- [ ] item~~) → ignored.
  - PR uses 'Refs #N' instead of 'Closes #N' → issue not checked.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request


def gh_get(path: str, token: str) -> dict | list:
    url = f"https://api.github.com/{path.lstrip('/')}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as exc:
        print(f"  GH API {exc.code} for {url}: {exc.read().decode()[:200]}")
        return {}


def parse_closing_refs(body: str) -> list[int]:
    """Extract issue numbers from Closes/Fixes/Resolves #N patterns."""
    if not body:
        return []
    pattern = r"(?:clos(?:es?|ed|ing)|fix(?:es|ed|ing)?|resolv(?:es?|ed|ing))\s+#(\d+)"
    return [int(n) for n in re.findall(pattern, body, re.IGNORECASE)]


def count_unchecked(body: str) -> list[str]:
    """
    Return list of unchecked AC items in the issue body.

    Skips:
    - Items crossed out: ~~- [ ] text~~  (intentionally dropped)
    - Lines inside ``` fences (code blocks)
    """
    if not body:
        return []
    unchecked: list[str] = []
    in_code_block = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if re.search(r"~~[^~]*\[ \][^~]*~~", line):
            continue
        if re.match(r"\s*[-*]\s+\[ \]\s+\S", line):
            unchecked.append(stripped)
    return unchecked


def main() -> int:
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        print("GH_TOKEN not set — skipping AC gate")
        return 0

    repo = os.environ.get("REPO", "")
    pr_body = os.environ.get("PR_BODY", "")

    if not pr_body:
        print("PR body is empty — nothing to check")
        return 0

    closing_refs = parse_closing_refs(pr_body)
    if not closing_refs:
        print("No closing references found — nothing to check")
        return 0

    print(f"Checking AC completeness for: {', '.join(f'#{n}' for n in closing_refs)}")
    failures: list[str] = []

    for issue_num in closing_refs:
        issue = gh_get(f"repos/{repo}/issues/{issue_num}", token)
        if not issue or not isinstance(issue, dict):
            print(f"  #{issue_num}: could not fetch — skipping")
            continue

        # Pull requests show up under /issues — skip them
        if "pull_request" in issue:
            print(f"  #{issue_num}: is a pull request — skipped")
            continue

        labels = [lbl["name"] for lbl in issue.get("labels", [])]
        if "ac-waiver" in labels:
            print(f"  #{issue_num}: has 'ac-waiver' label — skipped")
            continue

        title = issue.get("title", "")[:60]
        body = issue.get("body") or ""
        unchecked = count_unchecked(body)

        if not unchecked:
            print(f"  #{issue_num} '{title}': ✓ all ACs checked (or no checklist)")
        else:
            print(f"  #{issue_num} '{title}': {len(unchecked)} unchecked AC(s):")
            for item in unchecked[:5]:
                print(f"    • {item[:100]}")
            if len(unchecked) > 5:
                print(f"    … and {len(unchecked) - 5} more")
            failures.append(f"#{issue_num} — {len(unchecked)} unchecked ACs")

    if failures:
        print()
        print("❌ AC gate failed — referenced issues have unchecked acceptance criteria:")
        for f in failures:
            print(f"  {f}")
        print()
        print("Fix options:")
        print("  1. Check off completed ACs in the issue body ( - [ ] → - [x] )")
        print("  2. Cross out intentionally-dropped ACs  ( ~~- [ ] item~~ )")
        print("  3. File follow-up issues for remaining ACs; reference them in this PR body")
        print("  4. Add label 'ac-waiver' to the issue if the checklist is aspirational/stale")
        print("  5. Use 'Refs #N' instead of 'Closes #N' to keep the issue open")
        return 1

    print()
    print("✅ All closing references have complete AC checklists")
    return 0


if __name__ == "__main__":
    sys.exit(main())
