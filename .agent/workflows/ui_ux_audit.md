---
description: Run a rigorous Persona-driven UI/UX Audit on the frontend codebase
---
# UI/UX Persona Audit Workflow

Engineering code completion is not product completion. Run this workflow on frontend-heavy tasks to ensure the output meets "Executive Suite" aesthetic and functional standards.

1. **Authenticate Context**: Determine which UI page or component is currently being targeted/built.
2. **Read Persona Skills**: Invoke the `view_file` tool on the following persona profiles in `.agent/skills/`:
   - `data_viz_ux`
   - `edward_tufte`
   - `product_design_architect`
3. **Execute the "10-Foot Review"**: 
   - Analyze the UI for cognitive overload and poor visual hierarchy.
   - Attack "Chartjunk" (enforce the Data-Ink Ratio).
   - Verify affordances (do buttons look like buttons? is text readable?).
4. **Propose Fixes**: Generate an `implementation_plan.md` outlining specific, actionable structural and aesthetic changes without arbitrarily adding new engineering features. Focus on deletion, spacing, typography, and contrast.
5. **Notify User**: Present the audit findings to the user for sign-off before implementing the aesthetic refactors.
