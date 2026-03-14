---
description: Read the manuals to learn how to run the project (Read The Fucking Manual)
---

When the `/rtfm` command is invoked, you must immediately read the project's core documentation to understand how it is architected and how to run it. 

Follow these exact steps:

1. Use the `view_file` tool to read `/Users/andrewsmith/Documents/portfolio/nfl-dead-money/README.md`. This contains the executive summary, system architecture, and quickstart commands.
2. Use the `view_file` tool to read `/Users/andrewsmith/Documents/portfolio/nfl-dead-money/Makefile`. This defines all the executable commands used to operate the environment.
3. Use the `view_file` tool to read `/Users/andrewsmith/Documents/portfolio/nfl-dead-money/pipeline/README.md` if you are working on the Data/ML pipeline.
4. Use the `view_file` tool to read `/Users/andrewsmith/Documents/portfolio/nfl-dead-money/web/README.md` if you are working on the Next.js frontend.
5. Identify the exact `docker compose` or `make` commands specified in the documentation to run tests, scripts, or deploy the application. 
6. Do NOT try to run Python scripts or Node servers locally on the host unless the documentation explicitly permits it. Always favor the isolated Docker containers as instructed in the README.
