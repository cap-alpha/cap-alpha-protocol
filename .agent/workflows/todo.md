---
description: Parse user input or recent context to add new, prioritized tasks to the sprint plan.
---
# /todo Workflow

When the user runs `/todo <optional text>`, execute the following steps to triage and plan the work:

1. **Analyze Context**:
   - If the user provided text after the `/todo` command, parse that text as the primary directive.
   - If no text was provided, analyze the immediate preceding conversation history to infer the implicit request, broken feature, or missing functionality.

2. **Prioritize**:
   - Evaluate the inferred or explicit tasks against the current project state.
   - **CRITICAL RULE**: Fixing broken features, resolving compilation errors, and fixing failing tests MUST take absolute priority over new feature development.

3. **Update Sprint Plan**:
   - Locate the official Nexus project backlog at `docs/sprints/MASTER_SPRINT_PLAN.md`. 
   - Add the newly identified task(s) to the bottom of the current active Sprint checklist. If no Sprint exists, create a new one.
   - Break the task down into actionable, granular sub-tasks.
   - Prioritize bug fixes at the top of the newly generated list.

4. **Acknowledge**:
   - Briefly respond to the user confirming exactly what tasks were added to the persistent backlog and in what order of priority. Do not start executing the tasks unless the user explicitly chains it with `/go`.
