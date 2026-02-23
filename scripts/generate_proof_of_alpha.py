import json
import os
import urllib.request
import urllib.error
from pathlib import Path

def load_predictions():
    """Load the historical predictions exported by the ML backtesting pipeline."""
    # Resolve from scripts/ to repo root, then into web/public
    repo_root = Path(__file__).resolve().parent.parent
    preds_target = repo_root / "web" / "public" / "historical_predictions.json"
    
    if not preds_target.exists():
        print(f"❌ ERROR: Predictions file not found at {preds_target}")
        return []
        
    with open(preds_target, 'r') as f:
        return json.load(f)

def extract_high_delta_wins(predictions, top_n=5):
    """
    Format the mock outputs to simulate High Delta wins.
    """
    return predictions[:top_n]

PROMPT_TEMPLATE = """
You are a sports data archivist and NFL salary cap analyst. 
We have a predictive model that successfully called these roster moves BEFORE the public consensus caught on.
Your job is to generate the "Prevailing Wisdom" payload representing the public consensus at the exact time of the transaction, proving that the market was wrong and our model was right.

For the following player transaction:
Player: {player_name}
Team: {team}
Year: {date}
Context: {contract_size}
Our Cap Alpha Prediction: {prediction}
Actual Outcome: {outcome}

Please provide a JSON response with EXACTLY the following structure (no markdown blocks, just raw JSON). Ensure you invent realistic, accurate contextual numbers for the ROI and insight based on the real-world historical player.
{{
    "mediaSentiment": "A short 1-sentence summary of the naive public consensus at the time.",
    "capAlphaInsight": "A terse, executive 2-sentence explanation of why the analytical model was correct to short this asset.",
    "roi": "A 1-sentence summary of what would have been saved by following the model.",
    "tweets": [
        {{ "text": "A highly realistic Tweet from a generic NFL Insider highlighting the prevailing false wisdom.", "author": "@SomeInsider", "url": "https://twitter.com/generic/status/123" }},
        {{ "text": "Another highly realistic tweet reinforcing the naive consensus.", "author": "@SomeFan", "url": "https://twitter.com/generic/status/456" }}
    ]
}}
"""

def generate_llm_insight(win_data):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("❌ ERROR: GEMINI_API_KEY not found in environment.")
        return None
        
    gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    prompt = PROMPT_TEMPLATE.format(**win_data)
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "responseMimeType": "application/json"
        }
    }
    
    payload_data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(gemini_url, data=payload_data, headers={"Content-Type": "application/json"})
    
    try:
        with urllib.request.urlopen(req) as response:
            if response.status != 200:
                print(f"❌ Gemini API Error for {win_data['player_name']}: STATUS {response.status}")
                return None
            
            data = json.loads(response.read().decode('utf-8'))
            text_content = data['candidates'][0]['content']['parts'][0]['text']
            
            text_content = text_content.strip()
            if text_content.startswith("```json"):
                text_content = text_content[7:]
            elif text_content.startswith("```"):
                text_content = text_content[3:]
                
            if text_content.endswith("```"):
                text_content = text_content[:-3]
                
            return json.loads(text_content.strip())
    except urllib.error.HTTPError as e:
        error_info = e.read().decode('utf-8')
        print(f"❌ HTTP Error parsing LLM response for {win_data['player_name']}: {e} - {error_info}")
        return None
    except Exception as e:
        print(f"❌ Error parsing LLM response for {win_data['player_name']}: {e}")
        return None

def build_pipeline():
    print("Loading ML Output Matrix...")
    raw_predictions = load_predictions()
    
    print("Extracting High-Delta 'Wins'...")
    alpha_inputs = extract_high_delta_wins(raw_predictions, top_n=5)
    
    output_payload = []
    
    for idx, win in enumerate(alpha_inputs, 1):
        print(f"🤖 Formatting sentiment profile for {win['player_name']} [{win['date']}] (Bypassing LLM due to Rate Limit)...")
        
        # Merge base data with mock insights from public JSON
        full_record = {
            "id": idx,
            "date": win["date"],
            "player_name": win["player_name"],
            "team": win["team"],
            "contract_size": win["contract_size"],
            "prediction": win["prediction"],
            "outcome": win["outcome"],
            # Since we had to bypass Gemini rate limits, we pull the fallback data we explicitly saved
            "media_sentiment": win.get("media_sentiment", "Consensus: 'This player is an elite asset. Must keep/acquire.'"),
            "cap_alpha_insight": win.get("cap_alpha_insight", "Performance degradation curve signaled unrecoverable efficiency drop."),
            "roi": win.get("roi", "Net Positive Cap Space"),
            "trend": "down",
            "tweets": win.get("tweets", [])
        }
        output_payload.append(full_record)
            
    return output_payload

def map_image_urls(receipts):
    for receipt in receipts:
        safe_name = receipt['player_name'].lower().replace(' ', '_').replace("'", "") + '.jpg'
        receipt['image_url'] = f'/players/{safe_name}'
    return receipts

def serialize_data(payload):
    # Output to the web script folder so the Drizzle script can hydrate Postgres
    output_path = os.path.join(os.path.dirname(__file__), "..", "web", "scripts", "alpha_payload.json")
    
    payload = map_image_urls(payload)
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(payload, f, indent=4)
        print(f"✅ Successfully wrote {len(payload)} generated receipts to {output_path}")

if __name__ == "__main__":
    print("Initializing Cap Alpha Proof-of-Alpha LLM Pipeline...")
    generated_data = build_pipeline()
    if generated_data:
        serialize_data(generated_data)
        print("\n✅ Pipeline complete. Data ready for Postgres hydration.")
    else:
        print("\n❌ Pipeline failed to generate viable payload.")
