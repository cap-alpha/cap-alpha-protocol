# Sprint 02: Cap Alpha RAG Ingestion (Data Team)

**Target Date:** March 1, 2026
**Objective:** Stand up the backend Retrieval-Augmented Generation (RAG) vector store and Text-to-SQL capability to enable natural language queries against the Cap Alpha Protocol.

## 1. Vector Database Provisioning & Orchestration Config
- **Task:** Finalize the storage layer and embedding model configuration.
- **Technical Spec:** 
    - Database: Local `ChromaDB` (persistent client stored at `./data/chroma_db`).
    - Python Packages: `langchain`, `langchain-google-genai`, `chromadb`, `markdown-it-py`.
    - Embedding Model: Use Google `gemini-embedding-exp-03-07` or `text-embedding-004`.
- **Acceptance Criteria:** A test script (`test_chroma.py`) successfully writes a dummy document and executes a similarity search `k=3` returning the document.

## 2. Unstructured Markdown Ingestion (Context Pipeline)
- **Task:** Build the ingestion engine that physically reads our strategic artifacts and converts them to searchable vectors.
- **Technical Spec:** 
    - **Target Path:** `pipeline/scripts/nlp_sentiment_ingestion.py`
    - **Sources:** Iterate through `/reports` (specifically `model_miss_analysis.md`) and `/artifacts/reporting`.
    - **Chunking Logic:** Use LangChain's `MarkdownHeaderTextSplitter` to split on `##` and `###`, ensuring that contextual hierarchy (like "False Positives") remains attached to the player names in the tables. 
    - **Idempotency:** Implement an `md5` hash check of the document content against a SQLite cache table to skip re-embedding unchanged documents.
- **Acceptance Criteria:** The script logs "Ingested N chunks" and successfully writes to ChromaDB without duplicating existing vectors on a re-run.

## 3. Structured Data Bridge (DuckDB Text-to-SQL)
- **Task:** Equip the agent with the ability to dynamically write and execute SQL against our `gold` layer to answer purely quantitative questions without hallucination.
- **Technical Spec:**
    - **Target Path:** `pipeline/src/sql_agent_bridge.py`
    - **Schema Injection:** Extract the `SHOW ALL TABLES` and `DESCRIBE fact_player_efficiency` DDL from DuckDB.
    - **Prompt Engineering:** Create a strictly formatted System Prompt: `"You are a Postgres/DuckDB SQL expert. Given the following schema for fact_player_efficiency, construct a SQL query to answer the user's question..."`
    - **Execution Guardrails:** The Python executor must wrap `con.execute(sql).df()` in a `try/except` block and feed database schema errors *back* to the LLM so it can self-correct its query.
- **Acceptance Criteria:** `sql_agent_bridge.py "What is the total fair market value of Patrick Mahomes in 2024?"` returns a numeric value directly from the `fact_player_efficiency` table.

---
**Sign-off / Status:** 
- [ ] Planning Approved
- [ ] In Progress
- [ ] Completed
