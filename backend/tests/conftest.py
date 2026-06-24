"""
conftest.py — pytest configuration and fixtures for Life2Tea backend.
"""

import sys
import os
import pytest
from fastapi.testclient import TestClient

# Add backend directory to Python path
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.main import app


@pytest.fixture(scope="module")
def client():
    """Create a FastAPI test client."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="function")
def temp_config_dir(tmp_path):
    """Create a temporary config directory for testing."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    
    # Write a minimal global config
    import json
    config = {
        "llama_backend_dir": "",
        "models_dir": "",
        "default_port_range": [8080, 8099],
        "default_host": "127.0.0.1",
    }
    (config_dir / "global.json").write_text(
        json.dumps(config, indent=2),
        encoding="utf-8"
    )
    
    yield str(config_dir)
