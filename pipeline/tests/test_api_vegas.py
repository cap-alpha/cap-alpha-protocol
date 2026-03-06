import pytest
pytest.importorskip("fastapi")

from fastapi.testclient import TestClient
import sys
import os

# Add pipeline root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from pipeline.api.main import app

client = TestClient(app)

def test_vegas_endpoint():
    print("Testing /analyze/vegas...")
    
    qb_asset = {
        "id": "mahomes",
        "name": "Patrick Mahomes",
        "type": "player",
        "position": "QB",
        "surplus_value": 30.0,
        "risk_score": 0.1
    }
    
    payload = {
        "team_a": "KC",
        "team_b": "LV",
        "team_a_assets": [qb_asset], # KC sending Mahomes
        "team_b_assets": []
    }
    
    response = client.post("/api/analyze/vegas", json=payload)
    
    if response.status_code != 200:
        print(f"❌ FAIL: Status {response.status_code}")
        print(response.text)
        return

    data = response.json()
    print("Response:", data)
    
    # Check KC impact (Getting nothing, losing Mahomes)
    # 30 surplus * 10 weight = 300. / 50 = 6 Wins.
    # So KC wins should change by -6.0
    
    kc_impact = data.get("KC")
    if kc_impact and kc_impact["delta_wins"] == -6.0:
        print("✅ PASS: KC Win Total dropped correctly.")
    else:
        print(f"❌ FAIL: KC Data incorrect: {kc_impact}")

if __name__ == "__main__":
    try:
        test_vegas_endpoint()
    except ImportError:
        print("⚠️ SKIPPED: httpx/TestClient not installed.")
