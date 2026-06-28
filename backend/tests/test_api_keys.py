"""
test_api_keys.py — Unit tests for API Key management.

Tests:
  - Key generation with UUID and hash
  - Key storage and retrieval
  - Key revocation
  - Key expiration
  - Scope validation
"""

import time
from unittest.mock import MagicMock

from app.core.api_keys import ApiKey, ApiKeyManager, Scope


class TestApiKeyModel:
    def test_create_key(self):
        key = ApiKey.create(
            name="test-key",
            scopes=[Scope.READ, Scope.WRITE],
            expires_in_days=30,
        )
        assert len(key.id) == 16  # 8-byte hex
        assert len(key.hashed_key) == 64  # SHA256 hex
        assert key.name == "test-key"
        assert Scope.READ in key.scopes
        assert Scope.WRITE in key.scopes
        assert key.created_at > 0
        assert key.expires_at is not None
        assert key.remaining_days == 30

    def test_is_expired(self):
        key = ApiKey.create(name="test", scopes=[Scope.READ], expires_in_days=30)
        assert not key.is_expired

        expired_key = ApiKey.create(
            name="expired",
            scopes=[Scope.READ],
            expires_in_days=-1,  # Past
        )
        assert expired_key.is_expired

        never_expires = ApiKey.create(
            name="never",
            scopes=[Scope.READ],
            expires_in_days=None,
        )
        assert not never_expires.is_expired

    def test_to_dict(self):
        key = ApiKey.create(name="test", scopes=[Scope.READ])
        data = key.to_dict()

        assert data["id"] == key.id
        assert data["name"] == "test"
        assert "read" in data["scopes"]
        assert data["created_at"] == key.created_at
        assert data["revoked"] is False


class TestApiKeyManager:
    def test_init(self):
        config_mgr = MagicMock()
        manager = ApiKeyManager(config_mgr)
        assert manager._keys == {}

    def test_generate_key(self):
        config_mgr = MagicMock()
        manager = ApiKeyManager(config_mgr)

        plain_key, key_obj = manager.generate_key(
            name="test",
            scopes=[Scope.READ],
        )

        assert plain_key is not None
        assert key_obj.id in manager._keys
        assert manager.get_key_by_id(key_obj.id) == key_obj

    def test_revoke_key(self):
        config_mgr = MagicMock()
        manager = ApiKeyManager(config_mgr)

        plain_key, key_obj = manager.generate_key("test", [Scope.READ])
        assert not key_obj.revoked

        manager.revoke_key(key_obj.id)
        assert key_obj.revoked

    def test_delete_key(self):
        config_mgr = MagicMock()
        manager = ApiKeyManager(config_mgr)

        plain_key, key_obj = manager.generate_key("test", [Scope.READ])
        assert key_obj.id in manager._keys

        manager.delete_key(key_obj.id)
        assert key_obj.id not in manager._keys

    def test_list_keys(self):
        config_mgr = MagicMock()
        manager = ApiKeyManager(config_mgr)

        manager.generate_key("key1", [Scope.READ])
        manager.generate_key("key2", [Scope.WRITE])

        keys = manager.list_keys()
        assert len(keys) == 2

    def test_verify_key(self):
        config_mgr = MagicMock()
        manager = ApiKeyManager(config_mgr)

        plain_key, key_obj = manager.generate_key("test", [Scope.READ])

        # Verify by hashed key
        result = manager.verify_key(f"Bearer {key_obj.hashed_key}")
        assert result == key_obj

        # Invalid key
        result = manager.verify_key("Bearer invalid")
        assert result is None

        # Revoked key
        manager.revoke_key(key_obj.id)
        result = manager.verify_key(f"Bearer {key_obj.hashed_key}")
        assert result is None

    def test_expired_key(self):
        config_mgr = MagicMock()
        manager = ApiKeyManager(config_mgr)

        plain_key, key_obj = manager.generate_key(
            "test",
            [Scope.READ],
            expires_in_days=-1,  # Past
        )

        result = manager.verify_key(f"Bearer {key_obj.hashed_key}")
        assert result is None


class TestApiKeyScopes:
    def test_scope_enum(self):
        assert Scope.READ.value == "read"
        assert Scope.WRITE.value == "write"
        assert Scope.CHAT.value == "chat:infer"
        assert Scope.ADMIN.value == "admin"

    def test_key_requires_admin_scope(self):
        key = ApiKey.create(name="admin", scopes=[Scope.ADMIN])
        assert Scope.ADMIN in key.scopes

        key2 = ApiKey.create(name="read", scopes=[Scope.READ])
        assert Scope.ADMIN not in key2.scopes
