"""Tests for precommit_pii_guard."""
import os
import subprocess
import sys
from pathlib import Path

PYTHON = sys.executable
HOOK = str(Path(__file__).resolve().parent.parent / "precommit_pii_guard.py")


def _run(args, cwd=None, env=None):
    p = subprocess.run([PYTHON, HOOK, *args], capture_output=True, text=True,
                       timeout=30, cwd=cwd, env=env)
    return p.returncode, p.stderr


def _env():
    return {k: v for k, v in os.environ.items() if k != "PII_GUARD_DENYLIST"}


def test_clean_tree_passes(tmp_path):
    (tmp_path / "a.md").write_text("Contact jane@example.com or 303-555-0100.\n")
    rc, err = _run(["--root", str(tmp_path)], cwd=tmp_path, env=_env())
    assert rc == 0, err
    assert "scanned 1 files" in err


def test_real_looking_email_blocked(tmp_path):
    (tmp_path / "a.md").write_text("mail someone@corp-mail.io today\n")
    rc, err = _run(["--root", str(tmp_path)], cwd=tmp_path, env=_env())
    assert rc == 1 and "a.md:1 [email]" in err
    assert "corp-mail" not in err  # matched text never echoed


def test_phone_blocked(tmp_path):
    (tmp_path / "a.md").write_text("call (212) 867-5309\n")
    rc, err = _run(["--root", str(tmp_path)], cwd=tmp_path, env=_env())
    assert rc == 1 and "[phone]" in err


def test_key_blocked(tmp_path):
    (tmp_path / "k.txt").write_text("-----BEGIN RSA PRIVATE KEY-----\n")
    rc, err = _run(["--root", str(tmp_path)], cwd=tmp_path, env=_env())
    assert rc == 1 and "[private-key]" in err


def test_denylist_file_and_env(tmp_path):
    dl = tmp_path / "deny.txt"
    dl.write_text("# c\n\n\\bZZTOP\\b\n")
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "d.md").write_text("ZZTOP\n")
    rc, _ = _run(["--denylist", str(dl), "--root", str(tree)], env=_env())
    assert rc == 1
    rc, _ = _run(["--root", str(tree)], cwd=tmp_path,
                 env=dict(_env(), PII_GUARD_DENYLIST=str(dl)))
    assert rc == 1


def test_no_builtins_only_uses_patterns(tmp_path):
    (tmp_path / "a.md").write_text("someone@corp-mail.io\n")
    rc, _ = _run(["--no-builtins", "--root", str(tmp_path)], cwd=tmp_path,
                 env=_env())
    assert rc == 0


def test_binary_skipped(tmp_path):
    (tmp_path / "b.bin").write_bytes(b"\xff\xfe\x00ZZTOP")
    rc, err = _run(["--pattern", "ZZTOP", "--root", str(tmp_path)])
    assert rc == 0 and "scanned 0 files" in err


def test_path_and_root_exclusive(tmp_path):
    rc, err = _run(["--path", "x", "--root", str(tmp_path)])
    assert rc == 1 and "mutually exclusive" in err
