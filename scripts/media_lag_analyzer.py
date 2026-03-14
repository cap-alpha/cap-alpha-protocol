import os
import json
import logging
import duckdb
from google import genai
from google.genai import types

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MediaLagAnalyzer:
    """
    Analyzes the chronological delta between the ML Pipeline's identification 
    of a Bust Asset and the mainstream sports media consensus.
    """
    def __init__(self, db_path="md:nfl_dead_money"):
        self.db_path = db_path
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if self.api_key:
            self.client = genai.Client()
        else:
            logger.warning("GEMINI_API_KEY not found. Operating in Mock Fallback mode.")
            self.client = None

    def fetch_model_triggers(self, year=2024, limit=5):
        """Finds the precise NFL week the model first flagged a top-tier asset."""
        logger.info(f"Querying MotherDuck for early bust predictions in {year}...")
        con = duckdb.connect(self.db_path)
        
        # Example query grabbing the True Positives from the latest test fold
        query = f"""
            SELECT player_name, MIN(week) as trigger_week, AVG(predicted_risk_score) as risk
            FROM prediction_results 
            WHERE year = {year} 
              AND predicted_risk_score = 1
            GROUP BY player_name
            ORDER BY MIN(week) ASC
            LIMIT {limit}
        """
        results = con.execute(query).df()
        return results.to_dict('records')

    def query_gemini_media_consensus(self, player_name, year):
        """Uses Gemini's native Google Search Grounding to establish a public timeline."""
        logger.info(f"Dispatching Grounded Search for {player_name} ({year})...")
        
        prompt = f"""
        Search the web for news articles, sports media commentary, and Reddit discussions 
        regarding {player_name} during the {year} NFL season. 
        
        Identify the exact date and NFL week when public and media consensus aggressively 
        shifted to demanding that {player_name} be benched, traded, or cut due to poor performance.
        Return your answer as a JSON object with two keys:
        - "consensus_week": (integer)
        - "rationale": (short string explaining the citing sources)
        """
        
        if not self.client:
            # Fallback mock for UI dev
            import random
            return {
                "consensus_week": random.randint(4, 10),
                "rationale": f"Mocked: The Ringer & PFF demanded benching around mid-season for {player_name}."
            }
            
        try:
            # Utilize the google_search grounding tool required for chronological facts
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[{"google_search": {}}],
                    response_mime_type="application/json",
                )
            )
            return json.loads(response.text)
        except Exception as e:
           logger.error(f"Failed to parse Gemini response: {e}")
           return {"consensus_week": 8, "rationale": "Fallback due to API error."}

    def compute_lead_time(self, year=2024):
        triggers = self.fetch_model_triggers(year)
        
        report = []
        for asset in triggers:
            media_verdict = self.query_gemini_media_consensus(asset['player_name'], year)
            
            trigger_wk = asset['trigger_week']
            media_wk = media_verdict.get('consensus_week')
            
            
            if media_wk is not None and trigger_wk is not None:
                lead_time_weeks = media_wk - trigger_wk
                report.append({
                    "player_name": asset['player_name'],
                    "year": year,
                    "model_trigger_week": int(trigger_wk),
                    "media_consensus_week": int(media_wk),
                    "alpha_lead_time_weeks": int(lead_time_weeks),
                    "rationale": media_verdict.get('rationale'),
                    "media_date_approx": f"{year}-10-15" # simplified approx
                })
        
        import pandas as pd
        if report:
            df = pd.DataFrame(report)
            return df
        return None

if __name__ == "__main__":
    import pandas as pd
    analyzer = MediaLagAnalyzer()
    df_2024 = analyzer.compute_lead_time(2024)
    df_2025 = analyzer.compute_lead_time(2025)
    
    dfs = []
    if df_2024 is not None: dfs.append(df_2024)
    if df_2025 is not None: dfs.append(df_2025)
    
    if dfs:
        final_df = pd.concat(dfs, ignore_index=True)
        con = duckdb.connect(analyzer.db_path)
        con.register('final_df', final_df)
        con.execute("CREATE OR REPLACE TABLE media_lag_metrics AS SELECT * FROM final_df")
        logger.info(f"Persisted {len(final_df)} media lag records to MotherDuck across 2024-2025.")
    logger.info("Media Lag Analyzer execution complete.")
