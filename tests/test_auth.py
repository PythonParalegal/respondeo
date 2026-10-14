"""
test_auth.py — regression tests for auth_manager.py

Only tests pure functions that do NOT touch Streamlit session_state.
UI-facing functions (check_login, require_role, show_user_info) are excluded
from the headless suite — they require a running Streamlit runtime.
"""
import hashlib
import pytest


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

class TestPasswordHashing:

    def test_bcrypt_hash_is_verifiable(self):
        import auth_manager
        h = auth_manager._hash_password("correct-horse-battery")
        assert auth_manager._verify_password("correct-horse-battery", h) is True

    def test_wrong_password_fails(self):
        import auth_manager
        h = auth_manager._hash_password("secret")
        assert auth_manager._verify_password("wrong", h) is False

    def test_bcrypt_hash_starts_with_dollar_two(self):
        import auth_manager
        h = auth_manager._hash_password("any-password")
        assert h.startswith("$2")

    def test_legacy_sha256_verifies(self):
        import auth_manager
        raw = "legacy-password"
        sha_hash = hashlib.sha256(raw.encode()).hexdigest()
        assert len(sha_hash) == 64
        assert auth_manager._verify_password(raw, sha_hash) is True

    def test_legacy_sha256_wrong_password_fails(self):
        import auth_manager
        sha_hash = hashlib.sha256(b"real-password").hexdigest()
        assert auth_manager._verify_password("wrong-password", sha_hash) is False

    def test_empty_stored_hash_returns_false(self):
        import auth_manager
        assert auth_manager._verify_password("anything", "") is False


# ---------------------------------------------------------------------------
# Role hierarchy
# ---------------------------------------------------------------------------

class TestRoleLevels:

    def test_admin_level(self):
        import auth_manager
        assert auth_manager._role_level("admin") == 3

    def test_manager_level(self):
        import auth_manager
        assert auth_manager._role_level("manager") == 2

    def test_reviewer_level(self):
        import auth_manager
        assert auth_manager._role_level("reviewer") == 1

    def test_unknown_role_returns_zero(self):
        import auth_manager
        assert auth_manager._role_level("guest") == 0

    def test_admin_outranks_manager(self):
        import auth_manager
        assert auth_manager._role_level("admin") > auth_manager._role_level("manager")

    def test_manager_outranks_reviewer(self):
        import auth_manager
        assert auth_manager._role_level("manager") > auth_manager._role_level("reviewer")


# ---------------------------------------------------------------------------
# User CRUD (patched auth_config.yaml)
# ---------------------------------------------------------------------------

class TestUserCrud:

    def test_create_user_and_verify_password(self, auth_config_file):
        import auth_manager
        auth_manager.create_user("alice", "p@ssw0rd", "Alice Liddell", "manager")
        config = auth_manager._load_config()
        assert "alice" in config["users"]
        stored = config["users"]["alice"]["password_hash"]
        assert auth_manager._verify_password("p@ssw0rd", stored) is True

    def test_create_user_role_stored(self, auth_config_file):
        import auth_manager
        auth_manager.create_user("bob", "secret", "Bob Smith", "reviewer")
        config = auth_manager._load_config()
        assert config["users"]["bob"]["role"] == "reviewer"

    def test_update_password(self, auth_config_file):
        import auth_manager
        auth_manager.create_user("carol", "old-pass", "Carol Jones", "reviewer")
        auth_manager.update_password("carol", "new-pass")
        config = auth_manager._load_config()
        stored = config["users"]["carol"]["password_hash"]
        assert auth_manager._verify_password("new-pass", stored) is True
        assert auth_manager._verify_password("old-pass", stored) is False

    def test_update_password_nonexistent_user_returns_false(self, auth_config_file):
        import auth_manager
        result = auth_manager.update_password("nobody", "irrelevant")
        assert result is False

    def test_update_role(self, auth_config_file):
        import auth_manager
        auth_manager.create_user("dave", "pass", "Dave", "reviewer")
        auth_manager.update_role("dave", "manager")
        config = auth_manager._load_config()
        assert config["users"]["dave"]["role"] == "manager"

    def test_delete_user(self, auth_config_file):
        import auth_manager
        auth_manager.create_user("eve", "pass", "Eve", "reviewer")
        auth_manager.delete_user("eve")
        config = auth_manager._load_config()
        assert "eve" not in config["users"]

    def test_multiple_users_coexist(self, auth_config_file):
        import auth_manager
        for name in ("u1", "u2", "u3"):
            auth_manager.create_user(name, "pass", name.upper(), "reviewer")
        config = auth_manager._load_config()
        assert set(config["users"].keys()) == {"u1", "u2", "u3"}

    def test_load_config_returns_empty_when_no_file(self, auth_config_file):
        import auth_manager
        # auth_config_file fixture points to a non-existent file
        config = auth_manager._load_config()
        assert config == {"users": {}}
