"""Trigger map for self-correction infrastructure.

See docs/specs/library_self_correction_design.md §3.1 and §11.1.
Edited continuously per Standing Order A. Source of truth for all
keyword-based reminders surfaced by UserPromptSubmit and PreToolUse hooks.

Schema per entry:
    id        — kebab-case stable identifier
    patterns  — list of case-insensitive regex patterns
    scope     — "prompt" | "tool" | "both"
    reminder  — multiline string injected as systemMessage when matched
"""

TRIGGERS = [
    {
        "id": "drift-correction-language",
        "patterns": [
            r"you (missed|forgot|didn't|did not)",
            r"we (covered|discussed) this",
            r"as (i |we )?(said|discussed) (before|already)",
            r"this is the \d+(st|nd|rd|th) time",
            r"\bagain, you\b",
            r"i (told|asked) you",
        ],
        "scope": "prompt",
        "reminder": (
            "The maintainer is correcting drift. Before responding to the substance:\n"
            "(a) Acknowledge the correction explicitly.\n"
            "(b) Check whether `.claude/triggers.py` has an entry whose\n"
            "    patterns would have caught this drift if they'd been there\n"
            "    a turn earlier.\n"
            "(c) If no matching entry exists, ADD ONE in this same turn,\n"
            "    alongside the substantive response.\n"
            "Per Standing Order A and `feedback_meta_recursive_defect.md`."
        ),
    },
    {
        "id": "preflight-drafting",
        "patterns": [
            r"\bpreflight\b",
            r"drafting (a |the )?preflight",
            r"writing.{0,20}preflight",
        ],
        "scope": "both",
        "reminder": (
            "Consult `docs/templates/preflight_drafting_checklist.md` (10-item "
            "self-check) + `docs/lessons/scope-expansion-probe.md` + "
            "`feedback_commit_bundling_principle.md` before finalizing."
        ),
    },
    {
        "id": "preflight-patch-revision",
        "patterns": [
            r"patch.{0,20}preflight",
            r"revis(e|ed|ion).{0,20}preflight",
            r"delta.?check",
        ],
        "scope": "both",
        "reminder": (
            "Patching a preflight? Before handoff, run the post-patch grep ritual:\n"
            "(a) Identify the OLD pattern's stems (renamed function name, flipped\n"
            "    option's phrases, old mechanism keywords, old count value).\n"
            "(b) `grep -niE \"<stems>\" preflight.md` — the -i is load-bearing\n"
            "    (capitalized header variants slip past case-sensitive sweep).\n"
            "    For count changes, ALSO grep the digit (`grep -nE \"\\b6\\b\"`)\n"
            "    in addition to the spelled word — counts get capitalized,\n"
            "    abbreviated, or spelled differently across sections.\n"
            "(c) Classify each hit: retrospective/explanatory (KEEP) vs\n"
            "    stale prescription (PATCH).\n"
            "(d) Patch any stale prescriptions BEFORE CLI handoff.\n"
            "Per `docs/lessons/fix-the-prose-miss-the-code-block.md` +\n"
            "`.claude/refresher.md` Slot 1. Pattern empirically validated three\n"
            "times in beta-2.16 incl. self-canonization at C7 v2→v3."
        ),
    },
    {
        "id": "partition-enumeration",
        "patterns": [
            r"\breconcil(e|es|ed|iation)\b",
            r"\bpartition(s|ed|ing)?\b",
            r"by construction",
            r"sum(s|med)? to",
            r"(must|should) equal(s)?\b",
            r"distinct[- ]?(doc|document|count)",
        ],
        "scope": "both",
        "reminder": (
            "Asserting a reconciliation / partition / count-identity? Before\n"
            "claiming it holds:\n"
            "(a) Enumerate EVERY cell of the underlying grid (e.g. all\n"
            "    decision x family combinations), not just the ones a fixture\n"
            "    happens to seed — the dropped cell is the bug.\n"
            "(b) Check the JOIN KEY / counting domain on each side: a per-row\n"
            "    or per-(group,member) SUM cannot equal a DISTINCT-document\n"
            "    count when membership overlaps (Flag #30 class).\n"
            "(c) Pin the identity with a regression test whose fixture\n"
            "    exercises the overlap / every-cell case, not the happy path.\n"
            "beta-2.16 S-1c B-1+B-2 double-catch. Candidate lesson "
            "(`feedback_partition_enumeration_discipline`); promote to "
            "`docs/lessons/` on recurrence."
        ),
    },
    {
        "id": "file-archival-or-move",
        "patterns": [
            r"\bgit mv\b",
            r"moving (files?|the (file|doc))",
            r"archive.{0,30}(commit|doc|preflight)",
            r"renam(e|ed|ing).{0,30}(file|doc|spec|preflight|module|\.md|\.py)",
        ],
        "scope": "both",
        "reminder": (
            "Verify file is git-tracked via `git ls-files`, NOT `ls`. "
            "See `docs/lessons/not-in-git-tracked-not-existent.md` + "
            "`docs/lessons/chain-of-moves-stale-refs.md` (re-check refs "
            "after each hop)."
        ),
    },
    {
        "id": "sprint-close",
        "patterns": [
            r"sprint[- ]close",
            r"closing (the )?sprint",
            r"release tag",
            r"\bcut.{0,5}tag\b",
            r"version tag",
        ],
        "scope": "both",
        "reminder": (
            "Tag-cut ordering: retrospective → audit-doc archival → context "
            "maintenance → merge → tag → push. See "
            "`docs/lessons/premature-release-tag.md`. Trigger Layer B audit "
            "(Standing Order G) is a hard gate before addendum commit lands."
        ),
    },
    {
        "id": "broaden-or-comprehensive-scan",
        "patterns": [
            r"\bbroaden\b",
            r"comprehensive (grep|scan|search)",
            r"scan (all|every)",
            r"all instances",
            r"re-?inventory",
        ],
        "scope": "both",
        "reminder": (
            "Grep-count discipline: paste actual grep command and output. "
            "Broaden-without-reinventory: after broadening, re-grep the "
            "broadened pattern against the patch itself. See "
            "`docs/lessons/grep-count-discipline.md` + "
            "`feedback_meta_recursive_defect.md`."
        ),
    },
    {
        "id": "audit-doc-sample-data",
        "patterns": [
            r"docs/audits/.*\.md",
            r"pii[_ -]guard",
            r"sample data",
        ],
        "scope": "both",
        "reminder": (
            "Drafting or editing commit-bound prose under `docs/audits/`? "
            "Use synthetic sample data (`ABC-000001`, `DOC-000100`, "
            "jane@example.com, 'Sample Matter'). The pre-commit "
            "secrets/PII guard (`.claude/hooks/precommit_pii_guard.py`) is "
            "a fallback. See `docs/lessons/synthetic-sample-data-in-docs.md`."
        ),
    },
    {
        "id": "hotfix",
        "patterns": [
            r"\bhotfix\b",
            r"patch (to|for)",
            r"emergency (fix|patch)",
        ],
        "scope": "both",
        "reminder": (
            "Bundle test: same root cause AND same fix pattern AND same "
            "hazard class — file proximity is NOT a bundling criterion. "
            "Run scope-expansion probe before bundling. See "
            "`feedback_commit_bundling_principle.md` + "
            "`feedback_no_loose_threads.md`."
        ),
    },
    {
        "id": "redaction",
        "patterns": [
            r"\bredact(ion|ing|ed|s)?\b",
            r"apply_redactions",
        ],
        "scope": "both",
        "reminder": (
            "IRON LAW: `apply_redactions()` ONLY in `5_Production.py` burn "
            "path. `add_redact_annot()` is the annotation overlay (visible "
            "but non-destructive). See "
            "`docs/references/PYMUPDF_PATTERNS.md` Known Gotcha #2."
        ),
    },
    {
        "id": "pst-libpff",
        "patterns": [
            r"\bPST\b",
            r"libpff",
            r"pypff",
            r"explode_pst",
        ],
        "scope": "both",
        "reminder": (
            "Use libpff as primary, COM as fallback. NEVER use "
            "`multiprocessing.Process` for libpff (Windows spawn re-imports "
            "Streamlit). Attachment B-tree corruption throws "
            "IOError/RuntimeError — use explicit try/except Exception. "
            "See `docs/references/LIBPFF_API_REFERENCE.md` + CLAUDE.md "
            "PST Extraction Architecture section."
        ),
    },
    {
        "id": "outlook-msg",
        "patterns": [
            r"\bOutlook\b",
            r"\bMAPI\b",
            r"\.msg\b",
            r"process_msg_batch",
        ],
        "scope": "both",
        "reminder": (
            "COM is not headless. `process_msg_batch` calls "
            "`pythoncom.CoInitialize()` directly without guard — "
            "Windows-only path. COM AddStore cleanup is critical "
            "(finally block must scan by filepath). See "
            "`docs/references/OUTLOOK_COM_REFERENCE.md`."
        ),
    },
    {
        "id": "opensearch",
        "patterns": [
            r"\bOpenSearch\b",
            r"\bindexing\b",
            r"search query.{0,20}(DSL|index)",
            r"\.keyword\b",
        ],
        "scope": "both",
        "reminder": (
            "Consult `docs/references/OPENSEARCH_PATTERNS.md` for `_source` "
            "field names, `.keyword` suffix rules, and bulk indexing "
            "patterns. Field schema is authoritative there, not in "
            "page-file code."
        ),
    },
    {
        "id": "tika-metadata",
        "patterns": [
            r"\bTika\b",
            r"metadata key",
            r"get_tika_data",
        ],
        "scope": "both",
        "reminder": (
            "Metadata key names vary by file format. Consult "
            "`docs/references/TIKA_METADATA_KEYS.md` for the fallback "
            "chain per format before mapping a field."
        ),
    },
    {
        "id": "closed-case",
        "patterns": [
            r"closed case",
            r"case_status",
            r"case is closed",
        ],
        "scope": "both",
        "reminder": (
            "Closed cases block ALL writes; reads stay open. Do NOT use "
            "`st.stop()` — render the full UI with write widgets disabled "
            "(`disabled=True`). See CLAUDE.md Key Architecture Rules."
        ),
    },
    {
        "id": "version-bump",
        "patterns": [
            r"version bump",
            r"project_ver",
            r"__version__",
            r"bump.{0,10}version",
        ],
        "scope": "both",
        "reminder": (
            "`__version__` bumps in `config.py` are PM/CLI-autonomous "
            "engineering mechanics (CLAUDE.md Standing Orders — Decision "
            "Routing): execute the bump and surface it in the landing "
            "summary + diff; do not propose-and-wait. Bumping still "
            "cascades to every `.py` file's `project_ver` header on next "
            "edit — keep them in sync. Escalate only if a bump carries "
            "release/legal signaling."
        ),
    },
    {
        "id": "permission-gate",
        "patterns": [
            r"permission gate",
            r"require_permission",
            r"require_role",
            r"# permission:",
        ],
        "scope": "both",
        "reminder": (
            "Use `auth_manager.require_permission('<name>')` with a "
            "`# permission:` annotation comment. `require_role()` was "
            "removed in beta-2.7a Phase 13. See CLAUDE.md Access Gate "
            "Convention."
        ),
    },
    {
        "id": "audit-hooks",
        "patterns": [
            r"log_audit\b",
            r"log_audit_batch",
            r"audit logging",
        ],
        "scope": "both",
        "reminder": (
            "`log_audit()` and `log_audit_batch()` are 'never-raise' "
            "contracts — always wrap in try/except in callers. See "
            "CLAUDE.md Key Architecture Rules."
        ),
    },
    {
        "id": "patching-pattern",
        "patterns": [
            r"patching.{0,30}(other|elsewhere|similar)",
            r"same (defect|issue|bug) (elsewhere|in other)",
            r"similar issue",
        ],
        "scope": "both",
        "reminder": (
            "Meta-recursive defect: patches frequently commit the defect "
            "class they're closing. After patching, re-grep the broadened "
            "pattern against the patch itself. See "
            "`feedback_meta_recursive_defect.md`."
        ),
    },
    {
        "id": "hook-output-contract",
        "patterns": [
            r"systemMessage",
            r"additionalContext",
            r"hookSpecificOutput",
            r"(UserPromptSubmit|PreToolUse|PostToolUse|SessionStart|SessionEnd|Stop)\b.{0,20}hook",
            r"\.claude[/\\]hooks[/\\]",
        ],
        "scope": "both",
        "reminder": (
            "Touching Claude Code hook I/O? The contract, verified against\n"
            "official docs 2026-06-10:\n"
            "(a) `systemMessage` renders in the terminal UI for the user and\n"
            "    NEVER reaches the model. Model-side injection requires\n"
            "    `hookSpecificOutput.additionalContext` (+ correct\n"
            "    `hookEventName`); plain stdout also works for SessionStart\n"
            "    and UserPromptSubmit only.\n"
            "(b) UserPromptSubmit input field is `prompt`, not `user_prompt`.\n"
            "(c) Verify at the CONSUMER, not the emitter: acceptance for any\n"
            "    context-injection change must assert the model-side field\n"
            "    (or observe receipt in a live session), not terminal\n"
            "    visibility. The original beta-2.16 implementation shipped\n"
            "    model-invisible for ~19 days because tests asserted the\n"
            "    emitter's own (wrong) output shape.\n"
            "Pinned by `.claude/hooks/tests/test_trigger_injector.py` +\n"
            "`test_session_refresher.py`. Re-verify against docs (they\n"
            "evolve) before changing any hook's JSON shape."
        ),
    },
]
