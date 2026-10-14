"""
Seed (or verify) the e2e_admin test user in auth_config.yaml.

Usage:  .venv/Scripts/python.exe tests/e2e/seed_test_user.py
Idempotent — safe to run repeatedly.
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

import yaml
import bcrypt

AUTH_CONFIG_PATH = os.path.join(PROJECT_ROOT, "auth_config.yaml")

TEST_USER = "e2e_admin"
TEST_PASS = "E2E_Test_Pass_42!"
TEST_NAME = "Playwright Bot"
TEST_ROLE = "admin"


def seed():
    if os.path.exists(AUTH_CONFIG_PATH):
        with open(AUTH_CONFIG_PATH, "r") as f:
            config = yaml.safe_load(f) or {"users": {}}
    else:
        config = {"users": {}}

    if TEST_USER in config["users"]:
        print(f"[OK] Test user '{TEST_USER}' already exists.")
        return

    config["users"][TEST_USER] = {
        "name": TEST_NAME,
        "password_hash": bcrypt.hashpw(TEST_PASS.encode(), bcrypt.gensalt()).decode(),
        "role": TEST_ROLE,
    }

    with open(AUTH_CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False)

    print(f"[CREATED] Test user '{TEST_USER}' added to {AUTH_CONFIG_PATH}")


if __name__ == "__main__":
    seed()
