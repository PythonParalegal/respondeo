"""Structural regression pin for the BYOS sync loops' per-iteration commit
contract (Flag #32, beta-2.17 C-d).

`pages/6_Sync.py` is a Streamlit page: module-level UI code makes it
unimportable under pytest. So we pin the contract structurally via AST
rather than by exercising the runtime (AST-over-import precedent:
beta-2.16 C6).

Contract: every `for` loop in 6_Sync.py whose body issues a write on a
BYOS sync connection (`pull_conn` / `push_conn`) via `.execute(...)` must
also `.commit()` that same connection inside the same loop body. A
single commit *after* the loop holds the write transaction open across
the whole batch — for the pull loop that self-collides with the nested
redaction-mark writers in `_annot_extract_to_marks` (the ~60s lock +
lost-state abort that is Flag #32); for the push loop it queues every
concurrent session's writes behind the copy loop.

Expected: exactly two loops match (the BYOS pull loop and push loop),
both compliant. The per-iteration loops elsewhere in the module
(`sync_pending_documents`, `pull_reviewed_documents`) use a plain `conn`
name and are intentionally outside this contract's watch set.
"""
import ast
import pathlib

TARGET = pathlib.Path(__file__).resolve().parent.parent / "pages" / "6_Sync.py"
WATCHED_CONNS = {"pull_conn", "push_conn"}


def _base_names_calling(node, method):
    """Set of `<name>` for every `<name>.<method>(...)` call within node's subtree."""
    names = set()
    for child in ast.walk(node):
        if (isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr == method
                and isinstance(child.func.value, ast.Name)):
            names.add(child.func.value.id)
    return names


def test_byos_sync_loops_commit_per_iteration():
    tree = ast.parse(TARGET.read_text(encoding="utf-8"))
    matched = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.For):
            continue
        writing_conns = _base_names_calling(node, "execute") & WATCHED_CONNS
        if not writing_conns:
            continue
        committing_conns = _base_names_calling(node, "commit")
        for conn in sorted(writing_conns):
            assert conn in committing_conns, (
                f"{conn}.execute() runs inside the for-loop at "
                f"6_Sync.py:{node.lineno} but no {conn}.commit() exists in "
                f"the same loop body — per-iteration commit contract "
                f"violated (Flag #32 regression)."
            )
            matched.append((conn, node.lineno))

    assert len(matched) == 2, (
        f"expected exactly 2 BYOS sync loops under the per-iteration commit "
        f"contract (pull_conn + push_conn), found {len(matched)}: {matched}"
    )
    assert {c for c, _ in matched} == WATCHED_CONNS, (
        f"expected both pull_conn and push_conn loops; matched {matched}"
    )
