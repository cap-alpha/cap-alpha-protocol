---
description: Continuous Integration (CI) - ensure logical, non-overlapping commits with 100% test coverage and no mocks.
---

# Continuous Integration (CI) Workflow

This workflow ensures that all code changes are cleanly separated into highly cohesive, non-overlapping commits, and that the codebase maintains 100% valid test coverage across all layers (Unit, E2E, Data Quality, Integration, UAT) with minimal mocking.

## Step 1: Analyze Current State
1. Run `git status` to identify all modified, added, and deleted files.
2. Run `git diff` and `git diff --cached` to deeply understand the exact lines changed.
3. Identify all the distinct "features," "fixes," or "chores" present in the working directory. Group the files mentally by these features.

## Step 2: Formulate a Commit Plan
- **Goal**: Each commit must represent ONLY ONE logical feature, fix, or chore.
- If multiple files were modified for the *same* feature, they should be grouped together in one commit.
- **Handling Overlap**: If a *single file* contains changes for *multiple distinct features*:
  - **Do not** just `git add <file>`.
  - **Agent Strategy**: Because interactive `git add -p` is very difficult to navigate in an automated, non-interactive shell environment, you should use the following approach to safely split the file:
    1. Save a copy of the fully modified file to a temporary location (e.g., `/tmp/mod_file.py`).
    2. Overwrite the actual file to only contain the changes for **Feature A** (reverting the lines for Feature B).
    3. Run necessary tests (see Step 3) to ensure Feature A works in isolation.
    4. `git add <file>` and execute the commit for Feature A.
    5. Overwrite the actual file again, restoring the changes for **Feature B** alongside Feature A.
    6. Run necessary tests to ensure Feature B works.
    7. `git add <file>` and execute the commit for Feature B.

## Step 3: Enforce 100% Test Coverage (No Mocks)
Before you commit ANY feature, you must prove it works and is fully tested.
1. **Write/Update Tests**: Ensure the feature has corresponding Unit, Integration, Data Quality, and Playwright E2E tests, depending on the affected layers.
2. **Minimize Mocks**: Do NOT use mocked data for internal database queries, internal service calls, or business logic. You may only mock strict 3rd-party external API boundaries (where rate limits or sandboxes demand it).
3. **Execute the Test Suites**:
   - *Unit & Integration (Backend)*: Run `pytest --cov=. --cov-report=term-missing`
   - *Unit & Integration (Frontend)*: Run `npm run test:coverage` (if applicable)
   - *Playwright E2E*: Run `npx playwright test`
   - *Data Quality & Business Logic*: Run `pytest tests/data_quality` and `pytest tests/integration`
4. **Verify 100% Coverage**: Review the coverage reports closely. If coverage of your *changed logic* is less than 100%, write the missing tests. Keep iterating until it hits 100% and all test suites pass green.

## Step 4: Execute the Commits
Once the isolated feature passes all tests and achieves 100% coverage:
1. Stage the precise files/changes for this feature: `git add <file1> <file2>`
2. Commit with a highly descriptive message, detailing *what* the commit does and *why*.
   Example: `git commit -m "feat(data-pipeline): add dead money calculation rules" -m "Added business logic for cap casualty tracking. Includes end-to-end test validation against DuckDB without mocked data."`

## Step 5: Repeat Until Clean
Repeat Steps 2-4 until the working directory is clean (`git status` shows nothing to commit) and every single changed line has been safely committed, tested, and tracked.

---

## 🛡️ Agent Guardrails to Prevent Tripping Up
*These are critical instructions for any agent running this workflow to prevent destructive actions or getting stuck.*

- **NEVER use catch-all adds**: Never run `git commit -a`, `git add .`, or `git add -A`. Always specify exactly what you are adding (`git add path/to/specific_file.py`).
- **Test Before Committing**: Run tests *before* staging and committing, not after. Committing broken code defeats the purpose of CI.
- **Beware of Stashed Mocking**: actively `grep` your test files for `mock` or `patch`. If you are mocking a local database call or an internal service, rewrite the test to use a real test database (like an in-memory DuckDB instance).
- **Run Tests Synchronously**: When using `run_command` to execute tests, make sure to set `WaitMsBeforeAsync` high enough (or wait for the process) so you can actually read the terminal output and parse the coverage percentages.
- **Do not get trapped in `git add -p`**: Interactive bash prompts freeze agents. Always use the file-swapping strategy in Step 2 if you must split commits within a single file.
