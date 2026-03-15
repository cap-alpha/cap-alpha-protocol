# NFL Dead Money: MotherDuck Data Lake Architecture

This Entity Relationship Diagram (ERD) maps the flow of data from raw external sources (Spotrac, Rumor Mill) into the strict Medallion Architecture (Bronze -> Silver -> Gold). 

The addition of the **Fan Consensus Engine** introduces a new high-value raw feed.

```mermaid
erDiagram

    %% -----------------------------------------------------
    %% EXTERNAL DATA SOURCES
    %% -----------------------------------------------------
    SpotracAPI ||--o{ bronze_player_contracts : "Scrapes"
    Twitter_Reddit ||--o{ bronze_media_sentiment : "Ingests"
    User_Clients ||--o{ bronze_fan_consensus : "Votes via Showcase"

    %% -----------------------------------------------------
    %% BRONZE LAYER (Raw Ingestion)
    %% -----------------------------------------------------
    bronze_player_contracts {
        string raw_json
        timestamp scraped_at
    }

    bronze_media_sentiment {
        string raw_text
        string source
        timestamp scraped_at
    }

    bronze_fan_consensus {
        string user_id "Clerk ID (if auth) or Session"
        int player_id
        string prediction_type "Buy, Sell, Hold, Short"
        timestamp voted_at
    }

    %% -----------------------------------------------------
    %% SILVER LAYER (Cleaned & Standardized)
    %% -----------------------------------------------------
    bronze_player_contracts ||--|| silver_contracts : "Parses"
    silver_contracts {
        int player_id PK
        string player_name
        float total_guarantees
        float aav
        int contract_years
    }

    bronze_media_sentiment ||--|| silver_nlp_scores : "Vectorizes (LLM)"
    silver_nlp_scores {
        int player_id FK
        float sentiment_score "-1.0 to 1.0"
        float volatility_multiplier
    }

    bronze_fan_consensus ||--|| silver_consensus_aggregation : "Aggregates"
    silver_consensus_aggregation {
        int player_id FK
        float public_buy_ratio "% of crowd buying"
        int total_votes
    }

    %% -----------------------------------------------------
    %% GOLD LAYER (Feature Store & ML Output)
    %% -----------------------------------------------------
    silver_contracts ||--o{ gold_feature_store : "Joins"
    silver_nlp_scores ||--o{ gold_feature_store : "Joins"
    silver_consensus_aggregation ||--o{ gold_feature_store : "Joins"

    gold_feature_store {
        int player_id PK
        string feature_vector
        date point_in_time
    }

    gold_feature_store ||--|| gold_ml_predictions : "Infers"
    gold_ml_predictions {
        int player_id FK
        float risk_score "Algorithm Prediction"
        string anomaly_flag
    }

    %% -----------------------------------------------------
    %% THE ALPHA DELTA (Application Layer)
    %% -----------------------------------------------------
    gold_ml_predictions ||--|| alpha_arbitrage_engine : "Calculates Spread"
    silver_consensus_aggregation ||--|| alpha_arbitrage_engine : "Calculates Spread"

    alpha_arbitrage_engine {
        int player_id FK
        float delta_score "ABS(Algorithm - Crowd)"
        boolean is_tradable_alpha
    }
```

### Table Definitions

**1. The `bronze` Schema:**
Stores immutable, append-only raw data. If our parsing logic breaks, we can always replay from Bronze. The new `bronze_fan_consensus` will record every individual click from the Fan Dashboard.

**2. The `silver` Schema:**
Where the magic happens. Types are enforced. Missing data is imputed. NLP text is crushed into floating-point vectors (`silver_nlp_scores`). Fan votes are aggregated into ratios (`silver_consensus_aggregation`).

**3. The `gold` Schema:**
The final product. This is practically a denormalized Feature Store. The `alpha_arbitrage_engine` is the mathematical difference between what the *System* predicts (`risk_score`) and what the *Crowd* believes (`public_buy_ratio`). Executives pay for access to high-delta assets.
