  ---
  description: Autonomous Sprint Task Execution Engine
  ---

  # /go Workflow Instructions
  // turbo-all

  When the user triggers the `/go` slash command, you must operate in full autonomous mode to execute the remaining sprint backlog. Follow this strict operational loop:

  1. **Locate the Next Task**: Open and read the official Nexus sprint document at `docs/sprints/MASTER_SPRINT_PLAN.md`. Find the very next task that is NOT marked as `[x]`, `[-]` (Deferred), `[b]` (Blocked), or `[/]` (In Progress). To prevent collisions in multi-agent runs, favor tasks in different
  technical domains or files than what other agents are actively working on.
  2. **Mark In-Progress & Claim**: Update `MASTER_SPRINT_PLAN.md` and mark the task as `[/]` (In Progress). You MUST append a claim tag (e.g. `(Claimed by Agent)`) to explicitly lock the task.
  3. **Execute Task**:
      - Leverage the `// turbo-all` directive globally. Do not ask for user permission to run standard bash commands, tests, or scripts.
      - If the task requires architectural design, draft it in `implementation_plan.md` first.
      - Write the code, run the necessary scripts, or configure the necessary infrastructure autonomously.
  4. **Validation & Resolution**:
      - You MUST run validation tests autonomously. If tests fail or commands error out, fix them autonomously by reading the terminal output. Do not notify the user until everything passes or you have failed 5 times in a row.
  5. **Handle Blockers**: If you encounter a hard blocker (e.g., missing third-party API keys, impossible OS constraints):
      - Mark the task as `[b]` (Blocked) in `MASTER_SPRINT_PLAN.md`.
      - Document the explicit blocker and move to the NEXT unblocked task in step 1 without alerting the user.
  6. **Mark Completed**: Once you have explicitly proven the task is done, mark the task as `[x]` (Completed) in `MASTER_SPRINT_PLAN.md`.
  7. **The Infinite Loop**: Immediately return to Step 1 and find the *next* task. Continue this loop until there are absolute zero actionable sprint tasks remaining in the `MASTER_SPRINT_PLAN.md` backlog. Do not stop to wait for praise. MOVE!

