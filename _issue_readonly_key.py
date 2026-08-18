"""
_issue_readonly_key.py — Issue a read-only API key for the Android monitor.

Usage:
    python3 _issue_readonly_key.py [name]

Creates (or reuses) an API key with ONLY the `read` scope and prints the
Bearer token. The token is the value the Android client sends in:
    Authorization: Bearer <token>
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))

from app.core.database import init_db, get_db
from app.core.api_keys import (
    Scope,
    init_api_key_manager,
    get_api_key_manager,
)

name = sys.argv[1] if len(sys.argv) > 1 else "android-monitor"

config_dir = os.path.join(PROJECT_ROOT, "config")
init_db(config_dir)
init_api_key_manager(get_db())

mgr = get_api_key_manager()

# Generate directly. NOTE: mgr.list_keys() crashes on legacy keys whose scopes
# contain values no longer in the Scope enum (e.g. "models"), so we avoid it.
plain, key = mgr.generate_key(name=name, scopes=[Scope.READ])
print("KEY_ID:", key.id)
print("BEARER_TOKEN:", plain)
print("SCOPES:", [s.value for s in key.scopes])
