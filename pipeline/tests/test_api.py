import pytest

pytest.importorskip("fastapi")

import sys
import os
from fastapi.testclient import TestClient

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.main import app


def test_health_check_via_client():
    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_evaluate_endpoint_structure():
    from fastapi.testclient import TestClient

    client = TestClient(app)

    payload = {
        "team_a": "KC",
        "team_b": "BUF",
        "team_a_assets": [{"id": "mahomes", "type": "player"}],
        "team_b_assets": [{"id": "allen", "type": "player"}],
    }

    response = client.post("/api/trade/evaluate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "grade" in data
    assert "reason" in data
    assert data["status"] == "accepted"
