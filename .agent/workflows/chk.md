---
description: Milestone Checkpoint & Context Handoff Preparation
---

When the user executes the `/chk` command, you MUST immediately freeze active development and perform a strict Nexus context handoff sequence. This physically maps your internal AI state onto the permanent file system to ensure the repository is perfectly synchronized for the next AI Agent:

1. **Synchronize Active Brain Artifacts:**
   Physically format and copy the latest current state of your internal `task.md` (Backlog), `implementation_plan.md` (Roadmap), and `walkthrough.md` (Chronology) artifacts directly into the repository under the `docs/agent_context/` directory (create the directory if it doesn't exist). 
   This is critical: your internal structured planning *does not* natively survive session termination. You MUST duplicate the text into physical `.md` files in the repository.
   
2. **Update the Onboarding Playbook:**
   Quickly review `docs/agent_onboarding_playbook.md` and the master `README.md`. Ensure any newly surfaced hardware constraints (like TCC permission blocks or M4 thermal throttling), new scripts (like `deploy_gcp_spot.sh`), or architectural shifts are explicitly codified in the playbook for the next incoming agent.

3. **Stage and Commit to Version Control:**
   // turbo-all
   Execute the following bash commands sequentially using the `run_command` tool to physically lock the repository state to GitHub:
   `git add .`
   `git commit -m "Nexus Handoff Checkpoint: Synchronized agent brain artifacts and sprint plans for seamless handoff."`
   `git push`

4. **Confirm Handoff Readiness:**
   Notify the user that the environment is fully sealed, pushed, and ready for immediate termination/restart. Inform them that the next agent invoking `/rtfm` will seamlessly inherit the precise architectural state you just left.
