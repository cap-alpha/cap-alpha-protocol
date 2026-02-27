# Cap Alpha RAG: Intelligence Assistant Architecture 

## 1. Executive Summary
This document outlines the architecture and execution plan for transitioning the **Cap Alpha Protocol** from a backend data pipeline (Medallion Architecture/DuckDB) into an interactive **Applied AI Decision Support System**. 

By implementing a **Retrieval-Augmented Generation (RAG)** layer atop the existing infrastructure, we will allow users to query complex financial data, historical trends, and risk models using natural language. This project explicitly demonstrates the capability to build robust, structured data pipelines that securely feed context into Generative AI models—the most sought-after skill for Applied AI Engineers in 2025/2026.

---

## 2. High-Value Use Cases (The "Why")

The goal is to prove you can connect LLMs to highly structured, proprietary data to solve business problems without hallucination.

### Use Case A: The "Red List" Explainer (Risk Analytics)
*   **Query User Input:** "Why is the Pittsburgh Steelers' roster considered high-risk in 2025?"
*   **System Action:** The RAG system queries DuckDB for PIT's `Efficiency Score`, fetches the latest `executive_red_list_audit.md` document, and retrieves T.J. Watt's specific salary figures.
*   **LLM Synthesis:** The LLM generates an executive summary explaining that PIT's risk is driven by an aging core absorbing $> \text{X}\%$ of the salary cap, citing the exact DuckDB figures.

### Use Case B: Historical Precedent Search (Decision Support)
*   **Query User Input:** "Show me examples of teams that purged more than $40M in dead money and how their Win% changed the following season."
*   **System Action:** The agent executes a SQL query against the `gold` Medallion layer to identify instances matching the criteria (e.g., Chicago Bears, Atlanta Falcons).
*   **LLM Synthesis:** Formats the returned data into a narrative response, detailing the impact of the "Discipline Tax" in those specific instances.

### Use Case C: Contract Negotiation Telemetry
*   **Query User Input:** "What is the expected capital exposure (ECE) if we sign Dak Prescott to a 4-year $240M deal?"
*   **System Action:** The system runs the input through the existing XGBoost inference model, calculates the decay curve based on historical QB performance data stored in DuckDB, and feeds the output to the LLM.
*   **LLM Synthesis:** Provides a structured breakdown of the risk profile over the 4 years, highlighting the specific "Time Bomb" year where liquidity drag maximizes.

---

## 3. Core Architecture

The system will utilize an **Agentic RAG** approach. Rather than blindly dumping documents into a vector database, it will intelligently choose between querying structured SQL (DuckDB) and unstructured text (Markdown Reports).

### 3.1 Data Foundation (The Context Engine)
1.  **Structured Data (DuckDB):** The existing `gold` Medallion tables in DuckDB remain the source of truth for all hard numbers (Salary, Performance, Efficiency Scores). 
2.  **Unstructured Data (Markdown):** Your Intelligence Reports, CBA rules, and qualitative risk signals are stored as Markdown documents.

### 3.2 Ingestion & Embedding Pipeline
*   **Framework:** LlamaIndex or LangChain (Python).
*   **Text Splitter:** Markdown-aware splitting to retain the semantic hierarchy (Headers, Tables) of your Intelligence Reports.
*   **Embedding Model:** `text-embedding-3-small` (OpenAI) or a fast local model like `BGE-M3` (HuggingFace) to vectorize the unstructured text.
*   **Vector Store:** **ChromaDB** or **Qdrant** (running locally via Docker or in-memory) to index the embedded documents.

### 3.3 The Orchestration Layer (The "Brain")
*   **LLM:** `gpt-4o-mini` or `Claude 3.5 Haiku` for fast, cost-effective reasoning.
*   **Query Routing (Crucial Step):** When a user asks a question, the LLM first determines the tool to use:
    *   *Need a precise number/stat?* -> Use the **DuckDB SQL Tool** (Text-to-SQL logic).
    *   *Need a qualitative explanation/history?* -> Use the **Vector Search Tool** (Query ChromaDB).
    *   *Need both?* -> Execute both and synthesize.

### 3.4 User Interface
*   **Frontend:** **Streamlit** (Python). Perfect for rapid prototyping data applications. Allows you to build a clean chat interface, display charts, and show the exact SQL query the system used (excellent for proving the system isn't hallucinating).

---

## 4. Work Breakdown (Sprint Plan)

This is designed to be executed efficiently over 3-4 weeks.

### Sprint 1: Foundation & The Vector Store (Days 1-5)
*   **Goal:** Stand up the basic RAG pipeline for your unstructured Markdown reports.
*   **Tasks:**
    *   Initialize Python environment (`uv` or `poetry`) with `langchain` / `llama-index` and `chromadb`.
    *   Write an ingestion script that reads all files in `artifacts/reporting/`, chunks them mathematically, embeds them, and stores them in Chroma.
    *   Write a simple terminal script to test semantic searching (e.g., User types "Kyler Murray risk", system returns the relevant chunks from the reports).

### Sprint 2: Text-to-SQL (The DuckDB Bridge) (Days 6-10)
*   **Goal:** Allow the LLM to query your existing structured database safely.
*   **Tasks:**
    *   Create a specialized LangChain Agent or LlamaIndex Query Engine equipped with a SQL execution tool.
    *   Give the Agent a system prompt containing the exact schema of your `gold_roster_summary` and `gold_team_financials` tables.
    *   Test the Text-to-SQL engine in the terminal: Provide a question, watch the LLM generate the SQL, execute it against DuckDB, and return the answer.

### Sprint 3: The Orchestrator & Streamlit UI (Days 11-15)
*   **Goal:** Build the single brain that chooses between the Vector Store and DuckDB, and wrap it in a UI.
*   **Tasks:**
    *   Implement the Router Agent (the logic that decides *which* data source to query).
    *   Build a simple `streamlit` application.
    *   Add a chat input box, a chat history window, and an "Under the Hood" expander that shows *how* the agent got the answer (Show the SQL query or the retrieved text chunks). *This is crucial for portfolio demonstrations.*

### Sprint 4: Hardening & Portfolio Integration (Days 16-20)
*   **Goal:** Make it look professional and immune to simple jailbreaks.
*   **Tasks:**
    *   Add guardrails: If a user asks about baseball or general programming, the agent must politely refuse and anchor back to the Cap Alpha dataset.
    *   Update the `nfl-dead-money` README to include screenshots and a GIF of the Streamlit app functioning.
    *   Document the "Applied AI" architecture in a new markdown file in the primary repo.

---

## 5. Technical Stack Summary

*   **Database:** DuckDB (Structured) / ChromaDB (Vectors)
*   **Orchestration:** LangChain or LlamaIndex (Python)
*   **Modeling:** OpenAI API (GPT-4o-mini + Embeddings)
*   **Frontend:** Streamlit
*   **Packaging:** Standardizing on `uv` or `poetry` for modern Python dependency management and reproducible local environments.
