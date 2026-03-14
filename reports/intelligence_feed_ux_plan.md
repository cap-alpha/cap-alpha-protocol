# "Health & Sentiment" UX Integration Plan

Based on the pipeline scripts (`ingest_nflverse_injuries.py` and `generate_sentiment_features.py`), we have rich, unstructured text data flowing into the database (Injury Status, Primary Injury, Media Narratives/Sentiment). 

We need to weave this into the `PlayerDetailView` in a way that provides immediate value to our personas (Fantasy Managers needing active/inactive status, GMs needing risk/leverage context).

## The Proposed Layout Updates

### 1. The Global Header (At-a-Glance Health)
*   **Action:** Add a persistent "Health Badge" next to the player's name in the main header of `player-detail-view.tsx`.
*   **Design:** A status-colored pill outline (e.g., Red for `Out`, Yellow for `Questionable`, Green for `Active`).
*   **Data Hook:** Pulls the most recent `report_status` and `report_primary_injury` from the `nflverse_injuries` table.
*   **Example:** `[ QUESTIONABLE • Hamstring ]`

### 2. The "Intelligence & Rumor Feed" (Right Column)
*   **Action:** Overhaul the mocked `<IntelligenceFeed />` component.
*   **Design:** A scrolling timeline feed.
*   **Data Hooks:** 
    *   **Health Events:** Plot historical injury designations as timeline nodes (e.g., "Oct 12, 2023: Listed OUT with Ankle Sprain").
    *   **Sentiment Events:** Once we wire up the LLM to summarize the Wikipedia/Media narratives, inject short bullet points into this feed (e.g., "Media Sentiment: Contract holdout rumors peaked in July").
    *   **Visual Distinction:** Use distinct icons (a medical cross for injuries, a megaphone for media rumors) to differentiate the feed items.

### 3. The Analytics RAG Module (The "Why?")
*   **Action:** Integrate a natural language query bar directly beneath the Fair Market Value (FMV) Chart.
*   **Design:** A sleek input field: *"Ask Cap Alpha about this player's value history..."*
*   **Data Hook:** This is where the 768-D Gemini embeddings from `nlp_sentiment_features_true` come into play. When a user asks "Why did his value tank in 2023?", the RAG system queries the vector database, identifies the clustered injury records from 2023, and synthesizes a response: *"Value dropped 30% in 2023 primarily due to a Grade 2 Hamstring strain causing him to miss 6 games..."*

## User Review Required

> [!IMPORTANT]
> **Layout Priority**
> The right column currently holds the `PositionDistributionChart`, the `IntelligenceFeed`, and the `HistoricalLedger`. 
> 
> To make the "Health & Sentiment" feed prominent without cluttering the UI, I propose we convert the bottom half of the right column into **Tabs**: `[ Intelligence & Health ] [ Historical Ledger ]`. This saves vertical space and reduces cognitive overload (Data-Ink Ratio). 

Do you approve of this modular Tab approach and the Health Badge in the header?
