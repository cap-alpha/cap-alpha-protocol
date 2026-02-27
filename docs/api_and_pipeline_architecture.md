# Cap Alpha Protocol: Architecture & API Reference

## 1. Internal Application API (Next.js Server Actions)
The frontend (`web/app`) communicates with the underlying models and structured datasets via Next.js Server Actions located in `web/app/actions.ts`.

### `getRosterData()`
*   **Purpose:** Fetches the full league roster with associated financial metrics and risk modeling.
*   **Returns:** `PlayerEfficiency[]` (Includes Cap Hit, Risk Score, Fair Market Value).
*   **Fallbacks:** Implements deterministic mocking for visualization stability if the DuckDB hydration pipeline fails or returns `$0` metrics.

### `getTeamCapSummary()`
*   **Purpose:** Aggregates roster data to the Franchise level.
*   **Returns:** Array of objects containing `total_cap`, `risk_cap`, and active contract counts per team. Used on the Executive Dashboard.

### `getTradeableAssets(team?: string)`
*   **Purpose:** Filters the roster down to objects formatted for the Adversarial Trade Engine module.
*   **Returns:** Flattened asset array featuring `surplus_value` and `dead_cap_millions`.

### `getPositionDistribution(position: string)`
*   **Purpose:** Generates histogram buckets for market context charts (e.g., comparing a QB to the broader QB market).
*   **Returns:** Array of structured buckets (`range`, `count`, `min`).

---

## 2. Platform Data Flow Diagram
This flowchart illustrates the holistic data architecture, spanning raw data scraping, Medallion layer processing in DuckDB, Machine Learning model training, and the newly integrated RAG capabilities.

```mermaid
graph TD
    %% -- Data Sources --
    subgraph Data Sources
        API_{"NFL APIs / Spotrac"} --> |Python Scrapers| RawJSON["Raw Data Dump"]
        Docs_{"Unstructured Intelligence"} --> Reports["Markdown Reports"]
    end

    %% -- Core Medallion Pipeline --
    subgraph Pipeline Backend
        RawJSON --> |"medallion_pipeline.py"| DuckDB_Bronze[("DuckDB: Bronze (Raw)")]
        DuckDB_Bronze --> |Cleaning & Type Casting| DuckDB_Silver[("DuckDB: Silver (Clean)")]
        DuckDB_Silver --> |"materialize_features.py"| FeatureStore{"Feature Matrix"}
        
        %% Model Training Loop
        FeatureStore --> |"train_model.py"| XGBoost["XGBoost Risk Model"]
        XGBoost --> |Predictions| DuckDB_Gold[("DuckDB: Gold (Analytics View)")]
    end

    %% -- RAG Assistant Integration --
    subgraph Intelligence Assistant (Agent)
        Reports --> |"nlp_sentiment_ingestion.py"| ChromaDB[("ChromaDB (Vectors)")]
        
        %% The Router
        Prompt["User Query"] --> LLM_Router{"Orchestrator"}
        
        %% Qualitative Path
        LLM_Router -- "Qualitative Query" --> ChromaDB
        ChromaDB --> |Retrieve Chunks| Synthesize["LLM Synthesis"]
        
        %% Quantitative Path
        LLM_Router -- "Quantitative Query" --> SQL_Agent["SQL Agent Bridge"]
        SQL_Agent --> DuckDB_Gold
        DuckDB_Gold --> |JSON Rows| Synthesize
    end

    %% -- Frontend App --
    subgraph presentation [Next.js Web Client]
        DuckDB_Gold --> |"actions.ts"| UI_Dashboard["Executive Dashboard UI"]
        Synthesize --> UI_Chat["Cap Alpha Intelligence Feed"]
    end
```

## 3. Data Flow Narrative
1.  **Ingestion:** Scrapers retrieve standard player contract and performance statistics, storing them in a data lake (JSON/CSV).
2.  **Medallion Processing:** The Python back-end loads these files into the Bronze DuckDB tables. Data flows through Silver (standardization) and finally rests in Gold, enriched by the `XGBoost Risk Model` with `risk_scores` and `fair_market_value`.
3.  **UI Hydration:** Server Actions pull from the `.duckdb` target (or a locally deployed JSON fallback for rapid frontend iteration) directly into React Server Components.
4.  **RAG Augmentation:** 
    *   *Structured:* Our Python SQL agent directly converts natural language to DuckDB statements against the `gold` tables.
    *   *Unstructured:* Our Markdown reports are chunked and embedded via `text-embedding-004` into local ChromaDB storage, allowing semantic correlation with real-time quantitative queries.
