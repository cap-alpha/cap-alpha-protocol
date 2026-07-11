#!/usr/bin/env python3
"""
claude_review.py — Adversarial PR reviewer using the Anthropic Python SDK.

Usage (CI):
    python scripts/claude_review.py \
        --diff-file <path>          \
        --pr-number <n>             \
        --repo <owner/repo>         \
        --gh-token <token>

Usage (local test):
    git diff HEAD~1..HEAD | python scripts/claude_review.py --diff-stdin --pr-number 0 --dry-run

Exit codes:
    0 — review posted (or --dry-run, or no findings)
    1 — unrecoverable error (not missing secret — that exits 0 with a warning)
"""

from __future__ import annotations

import argparse
import os
import sys
import textwrap
from pathlib import Path


# ── helpers ──────────────────────────────────────────────────────────────────

MAX_DIFF_LINES = 30_000
SKIP_LABEL = "skip-claude-review"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Claude adversarial PR reviewer")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--diff-file", metavar="PATH", help="Path to a file containing the diff")
    src.add_argument("--diff-stdin", action="store_true", help="Read diff from stdin")
    p.add_argument("--pr-number", required=True, type=int)
    p.add_argument("--repo", default="", help="owner/repo — required when posting")
    p.add_argument(
        "--gh-token",
        default=os.environ.get("GH_TOKEN", ""),
        help="GitHub token for posting the review comment. Defaults to $GH_TOKEN env var; avoid passing via CLI arg (leaks into shell history / process list).",
    )
    p.add_argument("--dry-run", action="store_true", help="Print review to stdout, do not post")
    p.add_argument("--labels", default="", help="Comma-separated list of PR labels (for skip check)")
    return p.parse_args()


def load_diff(args: argparse.Namespace) -> str:
    if args.diff_stdin:
        return sys.stdin.read()
    return Path(args.diff_file).read_text()


def check_skip_label(labels_csv: str) -> bool:
    labels = [l.strip() for l in labels_csv.split(",") if l.strip()]
    return SKIP_LABEL in labels


def count_diff_lines(diff: str) -> int:
    return diff.count("\n")


def build_prompt(diff: str) -> tuple[str, str]:
    """Return (system, user) prompt tuple."""
    system = textwrap.dedent("""\
        You are an adversarial code reviewer with deep expertise in Python, TypeScript/Next.js,
        SQL (BigQuery dialect), and CI/CD pipelines.

        Your ONLY job is to enumerate concrete correctness bugs, data integrity issues, or
        security problems in the provided diff.

        Rules:
        - Answer ONLY from the diff content. Refuse to invent context not present in the diff.
        - Skip stylistic nits, formatting, and purely cosmetic issues.
        - Skip issues that are clearly intentional design decisions (e.g. TODO comments the author
          left deliberately).
        - For each finding, assign a severity tag:
            [BLOCKER] — would cause a production failure, data loss, or security hole
            [NIT]     — minor correctness issue unlikely to affect production
        - If you find zero issues, respond with exactly: "No findings."
        - Format your response as a markdown list. One bullet per finding. Keep each bullet ≤ 3 lines.
        - Do NOT summarize the diff. Do NOT praise the author. Just the findings.
    """)
    user = textwrap.dedent(f"""\
        Review the following unified diff for correctness bugs.
        Diff length: {count_diff_lines(diff)} lines.

        ```diff
        {diff}
        ```
    """)
    return system, user


def call_claude(system: str, user: str) -> str:
    """Call Anthropic API with prompt caching on the system message."""
    import anthropic  # imported here so the script is importable even without the package

    api_key = os.environ["ANTHROPIC_API_KEY"]
    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},  # prompt-cache the static system msg
            }
        ],
        messages=[{"role": "user", "content": user}],
    )
    return response.content[0].text


def has_blockers(review_text: str) -> bool:
    return "[BLOCKER]" in review_text


def post_github_review(
    repo: str, pr_number: int, body: str, event: str, gh_token: str
) -> None:
    """Post a formal PR review (APPROVE, REQUEST_CHANGES, or COMMENT)."""
    import json
    import urllib.error
    import urllib.request

    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/reviews"
    payload = json.dumps({"body": body, "event": event}).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {gh_token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status not in (200, 201):
                raise RuntimeError(f"GitHub API returned {resp.status}")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GitHub API returned {exc.code}: {exc.reason}") from exc
    print(f"Review posted ({event}) to PR #{pr_number}.")


def format_review_body(review_text: str, event: str) -> str:
    verdict = "✅ No blockers found." if event == "APPROVE" else "🚫 Blockers found — see findings below."
    header = f"## Claude Review [advisory]\n\n{verdict}\n\n"
    footer = (
        "\n\n---\n"
        "_This review is advisory. "
        "Model: `claude-opus-4-7`. "
        "To skip: add the `skip-claude-review` label._"
    )
    return header + review_text + footer


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()

    # Secret gate — exit 0 with warning if not configured
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "WARNING: ANTHROPIC_API_KEY secret is not set. "
            "Claude review skipped. "
            "Ask the repo owner to add ANTHROPIC_API_KEY as a repository secret.",
            file=sys.stderr,
        )
        sys.exit(0)

    # Label-based skip
    if check_skip_label(args.labels):
        print(f"Label '{SKIP_LABEL}' found — skipping Claude review.", file=sys.stderr)
        sys.exit(0)

    diff = load_diff(args)

    # Size gate
    diff_lines = count_diff_lines(diff)
    if diff_lines > MAX_DIFF_LINES:
        print(
            f"Diff is {diff_lines} lines (limit {MAX_DIFF_LINES}) — skipping Claude review.",
            file=sys.stderr,
        )
        sys.exit(0)

    if not diff.strip():
        print("Empty diff — nothing to review.", file=sys.stderr)
        sys.exit(0)

    system, user = build_prompt(diff)
    print(f"Calling Claude (diff: {diff_lines} lines)…", file=sys.stderr)
    try:
        review_text = call_claude(system, user)
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: Claude API call failed — skipping review. ({exc})", file=sys.stderr)
        sys.exit(0)

    event = "REQUEST_CHANGES" if has_blockers(review_text) else "APPROVE"
    review_body = format_review_body(review_text, event)

    if args.dry_run or args.pr_number == 0:
        print(f"[{event}]\n{review_body}")
        sys.exit(0)

    if not args.repo or not args.gh_token:
        print("ERROR: --repo and --gh-token are required when not in --dry-run mode.", file=sys.stderr)
        sys.exit(1)

    try:
        post_github_review(args.repo, args.pr_number, review_body, event, args.gh_token)
    except Exception as exc:  # noqa: BLE001
        # Fail loudly: a silent exit-0 here produces a green workflow run with no
        # review actually posted, so blockers slip through. Exit non-zero and let
        # workflow-level `continue-on-error` decide whether to gate the merge.
        print(f"ERROR: Failed to post review — {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
