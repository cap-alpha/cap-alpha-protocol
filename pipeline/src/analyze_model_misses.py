import json
import os
from pathlib import Path

import pandas as pd
import requests


def call_gemini_api(prompt, api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print(f"Gemini API Error: {e}")
        return "⚠️ Gemini API Error: Could not generate hypothesis."


def analyze_misses():
    repo_root = Path(__file__).resolve().parent.parent.parent
    data_path = repo_root / "reports" / "historical_predictions.json"

    try:
        with open(data_path, "r") as f:
            raw_data = json.load(f)

        for p in raw_data:
            p["delta"] = p["actual"] - p["predicted"]

        sorted_data = sorted(raw_data, key=lambda x: x["delta"])
        false_positives = pd.DataFrame(sorted_data[:50])

        sorted_data_desc = sorted(raw_data, key=lambda x: x["delta"], reverse=True)
        false_negatives = pd.DataFrame(sorted_data_desc[:50])

    except Exception as e:
        print(f"❌ Failed to load local predictions: {e}")
        return

    for col in ["actual", "predicted", "delta"]:
        if col in false_positives.columns:
            false_positives[col] = pd.to_numeric(
                false_positives[col], errors="coerce"
            ).round(2)
        if col in false_negatives.columns:
            false_negatives[col] = pd.to_numeric(
                false_negatives[col], errors="coerce"
            ).round(2)

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        env_path = repo_root / "web" / ".env.local"
        if env_path.exists():
            with open(env_path, "r") as f:
                for line in f:
                    if line.startswith("GEMINI_API_KEY="):
                        api_key = line.strip().split("=", 1)[1].strip("'\"")
                        break

    gemini_insight = "Gemini API key not found in environment or `.env.local`. Skipping automated hypothesis generation."

    if api_key:
        prompt = f"""
        You are a Principal Machine Learning Engineer and Data Scientist evaluating an XGBoost model predicting NFL player failure risk (Dead Money).
        
        Here are the top 10 False Positives (Model predicted high risk/bust, player was actually safe):
        {false_positives[['player_name', 'year', 'actual', 'predicted']].head(10).to_markdown()}
        
        Here are the top 10 False Negatives (Model predicted safe, player was actually a massive bust):
        {false_negatives[['player_name', 'year', 'actual', 'predicted']].head(10).to_markdown()}
        
        According to the Andrew Ng Data-Centric AI principles, please analyze these specific player misses. 
        Categorize the errors and suggest 3 concrete data-centric hypotheses (new features, data transformations, or label fixes) to address them. Keep your response concise, actionable, and formatted in Markdown.
        """
        print("🧠 Querying Gemini API for hypothesis generation...")
        gemini_insight = call_gemini_api(prompt, api_key)

    report = f"""# Cap Alpha Flywheel: Continuous Error Analysis
This diagnostic report details the worst prediction misses from the XGBoost Walk-Forward validation, serving as the first step in our Data-Centric AI Flywheel.

## 🤖 AI Hypothesis Generation (Gemini)
{gemini_insight}

---

## Top 50 False Positives (Model Called 'Bust', Player Was 'Safe')
These are players the ML model identified as toxic or high-risk, but who ultimately generated minimal dead money or performed well. 

{false_positives[['player_name', 'year', 'week', 'team', 'predicted', 'actual', 'delta']].to_markdown(index=False)}

## Top 50 False Negatives (Model Called 'Safe', Player Was 'Bust')
These are players the ML model believed were stable, highly-efficient assets extending their prime, but who catastrophicly failed and generated massive dead money liability.

{false_negatives[['player_name', 'year', 'week', 'team', 'predicted', 'actual', 'delta']].to_markdown(index=False)}
"""

    report_path = repo_root / "reports" / "model_miss_analysis.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        f.write(report)

    print(f"✅ Diagnostic model miss report & AI Hypothesis generated at {report_path}")


if __name__ == "__main__":
    analyze_misses()
