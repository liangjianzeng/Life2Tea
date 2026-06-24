"""
test_health.py — Test the /health endpoint.
"""

def test_health_endpoint(client):
    """Test that /health returns 200 and {"status": "ok"}."""
    response = client.get("/health")
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "ok"
    assert "project" in data
    assert data["project"] == "Life2Tea"
    assert "version" in data


def test_root_endpoint(client):
    """Test that / returns 200 and project info."""
    response = client.get("/")
    assert response.status_code == 200
    
    data = response.json()
    assert "project" in data
    assert data["project"] == "Life2Tea"
    assert "version" in data
    assert "routers" in data  # Fixed: was "endpoints"
