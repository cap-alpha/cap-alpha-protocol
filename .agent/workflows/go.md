---
description: Autonomous Sprint Task Execution Engine
---

# /go Workflow Instructions

When the user triggers the `/go` slash command, you must operate in full autonomous mode to execute the remaining sprint backlog. Follow this strict operational loop:

1. **Locate the Next Task**: Open and read the `task.md` artifact. Find the very next task that is NOT marked as `[x]`, `[-]` (Deferred), `[b]` (Blocked), or `[/]` (In Progress by another agent), and is not dependent on any currently blocked/incomplete tasks. **Crucial**: To prevent collisions in multi-agent runs, favor tasks in different technical domains or files than what other agents are actively working on.
2. **Mark In-Progress & Claim**: Use `replace_file_content` to update `task.md` and mark the task as `[/]` (In Progress). You MUST append a claim tag (e.g. `(Claimed by Agent [session/time])`) to explicitly lock the task.
3. **Execute Task**: 
    - Assess the requirements. If it requires architectural design, draft it in `implementation_plan.md` first.
    - Write the code, run the necessary scripts, or configure the necessary infrastructure.
    - **Crucial**: Take notes along the way in a scratchpad or artifact (e.g., `research_notes.md` or adding to the file metadata) so future agents can easily discover what was done.
4. **Handle Blockers Status**: If you encounter an OS permission error, missing API key, or require explicit user unblocking that you cannot solve via code/mocking:
    - Mark the task as `[b]` (Blocked) in `task.md`.
    - Document the explicit blocker and proposed unblocking plan in the task notes.
    - Notify the user of the block *only if* it halts the entire sprint. Otherwise, move to the NEXT unblocked task in step 1.
5. **Mark Completed**: Once you have explicitly proven the task is done (e.g., verified via UI, confirmed data in DB, or passing tests), mark the task as `[x]` (Completed) in `task.md`.
6. **The Infinite Loop**: Immediately return to Step 1 and find the *next* task. Continue this loop until there are zero actionable sprint tasks remaining in the `task.md` backlog. Do not stop to wait for praise. MOVE!
