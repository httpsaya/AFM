from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

VALID_ID   = "720221554469"
INVALID_ID = "000000000000"

def test_counterparty_found():
    r = client.get(f"/counterparty/{VALID_ID}")
    assert r.status_code == 200
    data = r.json()
    assert data["tx_count"] > 0
    assert "top_partners" in data
    assert "monthly" in data

def test_counterparty_not_found():
    r = client.get(f"/counterparty/{INVALID_ID}")
    assert r.status_code == 404

def test_search_basic():
    r = client.get("/search?q=канцел")
    assert r.status_code == 200
    assert "results" in r.json()

def test_search_with_filters():
    r = client.get("/search?q=топливо&date_from=2024-01-01&date_to=2024-12-31&amount_min=1000")
    assert r.status_code == 200

def test_search_empty_query():
    r = client.get("/search?q=")
    assert r.status_code == 422

def test_anomalies_found():
    r = client.get(f"/counterparty/{VALID_ID}/anomalies")
    assert r.status_code == 200
    assert "anomalies" in r.json()

def test_anomalies_not_found():
    r = client.get(f"/counterparty/{INVALID_ID}/anomalies")
    assert r.status_code == 404
