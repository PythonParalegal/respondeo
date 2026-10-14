# Design Spec — Library Self-Correction Infrastructure

**Drafted:** 2026-05-22 (during beta-2.15 sprint-close window, before beta-2.16 sprint-open).

**Provisional sprint name:** `beta-2.16-meta` (the maintainer to finalize at sprint-open).

**Purpose:** Build a self-correcting wiring layer over the existing CLAUDE.md
+ docs/references/ + docs/lessons/ + auto-memory library, so that documented
disciplines actually fire when relevant — not just when I happen to remember
them. The library is well-structured; the wiring is the failure mode.

**Scope posture:** Meta-infrastructure. Adds hooks, living documents, and
Standing Order additions. Does not change product code; absorbs the
beta-2.16-backlog item S-2 (CI secrets/PII guard).
PM and CLI Claude both consume + maintain the infrastructure; the maintainer
reviews diffs at sprint-close.

**Origin:** Brainstorming session 2026-05-22, triggered by the maintainer observing
that I still miss instructions despite the library's depth. The
brainstorming surveyed documented misses across beta-2.11 through beta-2.15
(22 documented misses) and found that 45% of misses are TRIGGER gaps (rules
exist but don't fire), 27% are RECENCY decay, 18% are COMPREHENSION
(multi-instance / meta-recursive), 9% are CATALOG gaps, 9% are META. The
fix targets the dominant failure modes, not the smallest.

---

## §1 — Problem Statement

The current library has four tiers that I read at session start:

- **CLAUDE.md** — Standing Orders + architecture rules + dependency pointer table.
- **MEMORY.md auto-memory index** — ~40 one-liner pointers to feedback / project / reference memories.
- **Skill registry** — names + descriptions of installed skills.
- **In-repo references** — `docs/references/`, `docs/lessons/`, `docs/templates/`, `docs/retrospectives/` (NOT loaded at session start; only consulted when I notice they apply).

The dependency pointer table in CLAUDE.md is file-trigger keyed: "Consult
when touching X." This works when I'm editing a known file. It does NOT
work when:

1. I'm responding to a free-form question (no file edit in flight).
2. My task is in a sub-tree of work that doesn't visibly touch the
   triggering file.
3. The relevant lesson/reference was canonized 2+ sprints ago and has
   faded from active recall.
4. I'm about to do something (git mv, edit a sensitive file, cut a tag)
   without explicitly being told the action triggers a rule.

### 1.1 Documented miss inventory (from beta-2.11 through beta-2.15)

22 documented misses across 5 sprints. Categorized:

| Category | Count | % | What it means |
|----------|-------|---|---------------|
| TRIGGER | 10 | 45% | Rule exists but didn't fire (no event/keyword maps to it) |
| RECENCY | 6 | 27% | Knew it but discipline decayed over sprints |
| COMPREHENSION | 4 | 18% | Multi-instance/meta-recursive scan needed |
| CATALOG | 2 | 9% | Didn't know the rule existed |
| META | 2 | 9% | Workflow-shape issue, not a doc miss |

The CATALOG fix ("make the inventory more visible") would address only 9%.
Real leverage is in TRIGGER wiring and RECENCY counter-decay.

### 1.2 Top recurring patterns (informing initial refresher.md)

1. **Check 1 Not-in-git** — 5 recurrences across beta-2.11 / 2.13 / 2.15.
   Verify file tracked via `git ls-files`, not `ls`.
2. **Broaden-without-reinventory** — 6+ recurrences in beta-2.14-2.15.
   Patch closes defect class then commits same class elsewhere in fix.
3. **Hotfix-on-hotfix regression** — textbook example beta-2.13 Bates-batch.
4. **Manual pre-commit hygiene checks** — they don't scale.
5. **Post-tag housekeeping slips** — recurring across beta-2.9/2.10/2.11/2.13.

---

## §2 — Architecture

Four cooperating components, each handling a distinct miss category:

```
┌────────────────────────────────────────────────────────────────────┐
│  [1] UserPromptSubmit + PreToolUse hooks → trigger_injector.py     │
│      Reads .claude/triggers.py (keyword → reminder map)          │
│      Scans the maintainer's prompt AND Claude's tool args for matches      │
│      Injects pointer notes when fired                              │
│      Handles: TRIGGER gaps (45% of misses)                         │
└────────────────────────────────────────────────────────────────────┘
                              │
┌────────────────────────────────────────────────────────────────────┐
│  [2] SessionStart hook → session_refresher.py                      │
│      Reads .claude/refresher.md (top 5 recurring misses, curated)  │
│      Injects at every session start                                │
│      Handles: RECENCY decay (27%)                                  │
└────────────────────────────────────────────────────────────────────┘
                              │
┌────────────────────────────────────────────────────────────────────┐
│  [3] Pre-commit hooks (Tier 4 promotion targets)                   │
│      Check 1 verification, secrets/PII guard (absorbed S-2)        │
│      Handles: COMPREHENSION (binary-checkable subset)              │
└────────────────────────────────────────────────────────────────────┘
                              │
┌────────────────────────────────────────────────────────────────────┐
│  [4] CLAUDE.md Standing Orders + preflight-drafting-checklist      │
│      Triggers/refresher maintenance, promotion ladder, judgment    │
│      checklist items                                               │
│      Handles: COMPREHENSION (judgment-needed) + maintenance        │
└────────────────────────────────────────────────────────────────────┘
```

**Visibility:** When a trigger or refresher fires, the injected context
includes a visible header (`[Trigger fired: id1, id2]`) so the maintainer and I can
both audit whether the wiring is firing — silence would let the system go
stale invisibly.

---

## §3 — Component Designs

### 3.1 Trigger Injection — `.claude/triggers.py`

Curated keyword → reminder map. Living document; updated continuously
(see Standing Order A in §4).

> **Implementation note:** Triggers are stored as a Python module (`.claude/triggers.py`) — a list of dicts with the same fields. Switch from YAML avoids adding PyYAML dependency per Supply Chain Security Standing Order. Schema below describes the conceptual structure; actual code uses Python literals.

**Schema (per entry):**

```yaml
- id: <kebab-case-stable-id>
  patterns:
    - <regex 1, case-insensitive, word-boundary>
    - <regex 2>
  scope: prompt | tool | both   # default: both
  reminder: |
    <terse pointer to the relevant lesson / reference / Standing Order.
    Cite file paths. Do NOT inline the full content — link, don't copy.>
```

**Match semantics:** Case-insensitive regex with explicit word boundaries
where needed. Patterns should be specific enough not to false-match
unrelated prose ("file" alone is too broad; "git mv" or "moving files"
is appropriate).

**Scope field:**
- `prompt` — only scan user input (the maintainer's messages)
- `tool` — only scan tool call arguments (Bash commands, Edit/Write paths)
- `both` — scan both (default)

Why two scopes: the maintainer's prompts use casual language; phrases like "moving these
files" might not match. My tool calls are deterministic — `Bash: git mv X Y`
is exact. The `tool` scope catches Claude drift before I act; the `prompt`
scope catches the maintainer's intent before I respond.

**Initial MVP set (16 entries — 15 domain + 1 meta):**

| id | scope | triggers on | reminder points to |
|----|-------|-------------|--------------------|
| **drift-correction-language** (meta) | prompt | "you missed/forgot/didn't", "we covered this", "again, you", "this is the Nth time" | §11.1 + `feedback_meta_recursive_defect.md` — surfaces system's own maintenance need (Layer A of §11) |
| preflight-drafting | both | "preflight", "drafting preflight" | preflight_drafting_checklist + scope-expansion-probe + commit-bundling-principle |
| file-archival-or-move | tool primary | "git mv", "moving file", "archive doc/commit", "rename" | not-in-git-tracked-not-existent + chain-of-moves-stale-refs |
| sprint-close | prompt primary | "sprint close", "release tag", "cut tag" | Tag-cut ordering Standing Order + premature-release-tag lesson |
| broaden-or-comprehensive-scan | both | "broaden", "comprehensive scan", "all instances" | grep-count-discipline + meta-recursive-defect |
| hotfix | both | "hotfix", "patch for/to" | commit-bundling-principle + scope-expansion-probe |
| redaction | both | "redact", "apply_redactions" | PYMUPDF_PATTERNS Iron Law (`apply_redactions` ONLY in 5_Production.py burn) |
| pst-libpff | both | "PST", "libpff", "pypff" | LIBPFF_API_REFERENCE + CLAUDE.md PST Extraction Architecture section |
| outlook-msg | both | "Outlook", "MAPI", ".msg" | OUTLOOK_COM_REFERENCE + COM threading rules |
| opensearch | both | "OpenSearch", "indexing", "search query" | OPENSEARCH_PATTERNS |
| tika-metadata | both | "Tika", "metadata key" | TIKA_METADATA_KEYS |
| closed-case | both | "closed case", "case_status" | CLAUDE.md write-block rule (no st.stop, render disabled) |
| version-bump | both | "version bump", "project_ver", "__version__" | version-tracking skill + project_ver cascade rule |
| permission-gate | both | "permission gate", "require_permission" | Access Gate Convention |
| audit-hooks | both | "log_audit", "audit logging" | never-raise contract (always wrap in try/except) |
| patching-pattern | both | "patching", "same defect elsewhere", "similar issue" | meta-recursive-defect |

The first entry (`drift-correction-language`) is structurally different
from the others — it's the bootstrap-closer described in §11.1. It MUST
ship in Commit 1 so Layer A is operational from day one.

**Hook script: `.claude/hooks/trigger_injector.py`** (~30-50 lines):

1. Determine event (UserPromptSubmit vs PreToolUse) from invocation context.
2. Read input (prompt text for UserPromptSubmit; tool args JSON for PreToolUse).
3. Load `.claude/triggers.py`.
4. Filter entries by scope matching the event.
5. For each remaining entry, regex-scan input.
6. Collect matched IDs + reminders.
7. If matches → stdout: `[Triggers fired: id1, id2]\n\n<reminder1>\n\n<reminder2>`
8. If no matches → exit 0 with no output.

**Hook registration in `.claude/settings.json`:**

```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "matcher": "", "hooks": [
        { "type": "command",
          "command": ".venv/Scripts/python.exe .claude/hooks/trigger_injector.py --event=UserPromptSubmit" }
      ]}
    ],
    "PreToolUse": [
      { "matcher": "", "hooks": [
        { "type": "command",
          "command": ".venv/Scripts/python.exe .claude/hooks/trigger_injector.py --event=PreToolUse" }
      ]}
    ]
  }
}
```

Implementation plan (next skill: writing-plans) will pin the exact stdin
contract and any required JSON output schema.

> **Post-ship correction (2026-06-10).** The shipped hooks emitted reminders
> via `systemMessage`, which renders only in the terminal UI and never reaches
> the model, and read UserPromptSubmit's `user_prompt` field, whose documented
> name is `prompt`. Both hooks now inject via
> `hookSpecificOutput.additionalContext` (with `hookEventName`) and keep
> `systemMessage` as a one-line user-visible audit header; the injector reads
> `prompt` (falling back to `user_prompt`) and suppresses a trigger id that
> already fired in the same session within 30 minutes. This supersedes the
> §6 "visible in initial context" acceptance criteria: tests must assert the
> model-side field, not the emitter's own output. Registration example:
> `.claude/settings.example.json`.

### 3.2 Session Refresher — `.claude/refresher.md`

Hand-curated, top 5 recurring misses. Refreshed at sprint-close (Standing
Order B in §4). Injected at every session start via the SessionStart hook.

**Initial content** (from §1.2 top recurring patterns):

```markdown
# Top recurring misses — refresh at every sprint-close

These are the failure modes that have recurred 3+ times across recent
sprints despite canonization. Keep them in active mind throughout this
session. If you catch yourself about to recur on one, STOP.

1. **Check 1 (Not-in-git).** Verify file tracked via `git ls-files`,
   NOT `ls`. `ls` shows filesystem contents — an untracked file passes.
   5 recurrences (beta-2.11 C8, beta-2.13 Hotfix 4, beta-2.15 C8). See
   `docs/lessons/not-in-git-tracked-not-existent.md`.

2. **Broaden-without-reinventory.** When patching N instances of pattern
   X, re-grep the patch ITSELF for pattern X before declaring done. The
   patch closing a defect class frequently commits the same class
   elsewhere in its fix. 6+ recurrences in beta-2.14-2.15. See
   `docs/lessons/grep-count-discipline.md` + auto-memory
   `feedback_meta_recursive_defect.md`.

3. **Scope-expansion probe before hotfix bundling.** Two hotfixes
   touching the same code path require a probe: would Hotfix A's
   change interact with Hotfix B's path? Textbook regression: beta-2.13
   Bates-batch (Hotfix 1's guard broke Hotfix 3's path). See
   `feedback_commit_bundling_principle.md` + `feedback_no_loose_threads.md`.

4. **Convention drift is real.** A documentation convention without CI
   enforcement decays within 2-3 sprints (beta-2.14 → beta-2.15). CI guard absorbed into this design;
   ships at Commit 2 (Tier 4 promotion of this slot).

5. **Post-tag housekeeping slips.** Sprint-close commits land before
   merge+tag, so Current State table / CHANGELOG often need a small
   follow-up on next sprint's branch. Anticipate; don't be surprised
   when sprint-open needs a housekeeping commit.
```

**Hook script: `.claude/hooks/session_refresher.py`** (~10 lines):

1. Read `.claude/refresher.md`.
2. Print to stdout. Claude Code injects as session-start context.

### 3.3 Pre-commit Hooks (Tier 4 promotion targets)

These ship as part of Commit 2 of the MVP (see §6). They are the first
three Tier 4 promotions: Check 1, secrets/PII guard (absorbed S-2),
broaden-without-reinventory.

**Check 1 hook (`.claude/hooks/precommit_check1.py`):**
- Reads the most recent preflight file in `docs/audits/` (if any).
- Extracts file paths cited in the preflight.
- Runs `git ls-files --error-unmatch` on each.
- If any cited path is untracked AND not in the staged add set → exit 1
  with a clear message naming the offending paths.
- This catches the specific failure mode of treating an in-session
  drafted file as if it's already tracked.

**Secrets/PII guard (`.claude/hooks/precommit_pii_guard.py`)** — this
is the absorbed S-2 work:
- Scans tracked text files for private keys, API tokens, real-looking
  email addresses and phone numbers, plus an optional local deny-list.
- If any rule matches → exit 1 (reporting file:line and rule only).

**Broaden-without-reinventory item is judgment, not binary** — promotes
to preflight-drafting-checklist Item 12 instead of a hook (see §3.4).

### 3.4 CLAUDE.md Standing Order Additions

Six edits to CLAUDE.md, named A-F:

**A. New Standing Order — Triggers & Refresher Living Documents**

> `.claude/triggers.py` is updated continuously, not on a schedule.
> When you catch yourself drifting (or the maintainer catches you), update the
> file in the same turn as the correction. Add a triggers.py entry
> with the keyword(s) that should have fired and the reminder you needed.
> The yaml is the durable record of recurring drift patterns; the goal
> is to make every miss caught once never miss again.
>
> `.claude/refresher.md` is updated at sprint-close. See Standing Order
> §Sprint-Close Refresher Review.

**B. New Standing Order — Sprint-Close Refresher Review**

Slots into existing sprint-close sequence between the retrospective and
audit-doc archival steps.

> For each slot in `.claude/refresher.md`:
> 1. Increment recurrence counter if pattern recurred this sprint.
> 2. Check promotion criteria (3+ recurrences across 2+ sprints AND
>    binary-checkable OR reducible to single checklist question).
> 3. If criteria met → **implement Tier 4 promotion in this sprint-close
>    commit**:
>    - Binary-checkable → add hook script + settings.json registration
>    - Judgment-required → add preflight-drafting-checklist item
>    - Log to `docs/discipline_graveyard.md` (date, pattern, mechanism,
>      recurrence count at promotion)
>    - Vacate slot in refresher.md
> 4. If slot has zero recurrence for 2 consecutive sprints → demote
>    (keep triggers.py entry, vacate refresher slot).
> 5. Cap at 5 slots forces hard prioritization: cannot add a new
>    pattern unless you promote or demote.

**C. Preflight-Drafting-Checklist Additions** (in
`docs/templates/preflight_drafting_checklist.md`)

> **Item 11 — Grep-count discipline.** If your preflight references a
> count (e.g., "3 sites use Pattern Y," "N occurrences of foo"), paste
> the exact grep command and its output count. Predictions without
> verification are deferral risk. (Pending since beta-2.12; canonized
> 2026-04 in `docs/lessons/grep-count-discipline.md`.)
>
> **Item 12 — Broaden-without-reinventory re-scan.** If your preflight
> broadens a pattern, scope, or fix scope, paste the output of
> re-grepping the broadened pattern against the patch itself. The patch
> closing a defect class frequently commits the same class elsewhere
> in its fix. (Canonized in `docs/lessons/grep-count-discipline.md`
> after 6 recurrences in beta-2.14-2.15.)

**D. CLAUDE.md Dependency API References Table Row**

> Add row:
> | `.claude/triggers.py`, `.claude/refresher.md`, `docs/discipline_graveyard.md` | Living self-correction infrastructure: keyword-trigger map, session-start refresher, and promotion graveyard log | When catching yourself drifting (update triggers.py inline); at sprint-close (refresh refresher.md per Standing Order); at Tier 4 promotion (log to graveyard) |

**E. Lesson Integration Decision Tree — New Step 1.5**

Insert BEFORE current step 2:

> **1.5. Is this a recurring drift pattern that should be wired into
> self-correction?** → Add an entry to `.claude/triggers.py`. This
> catches the pattern in real-time on future sessions. If pattern
> recurs despite triggers, promote to `.claude/refresher.md` per the
> Promotion Ladder Standing Order.

**F. ROADMAP_TODO.md Backlog Note**

> Mark "S-2 CI secrets/PII guard" as **absorbed
> into `library_self_correction_design.md`** rather than deferred. The
> secrets/PII guard ships as Commit 2 of the meta-sprint, not as
> standalone beta-2.16 scope.

**G. New Standing Order — Sprint-Close Triggers Audit (Layer B of §11)**

Slots into existing sprint-close addendum preflight as a hard gate item.

> **Triggers Audit (hard gate — required for sprint-close addendum
> commit to land).** For every miss documented in this sprint's
> retrospective §4 (or equivalent "dead ends," "corrections," "misses
> canonized" sections), list:
> - The miss (one line)
> - The `triggers.py` entry that would have caught it (by ID)
> - If no entry caught it: "ADDED → <new entry ID>" with the entry
>   appearing in the same commit diff
> - If intentionally not adding (e.g., one-off): "NOT ADDED because
>   <reason>"
>
> Paste this table as a section of the sprint-close commit message.
> Without it, the addendum commit cannot land. This closes the
> bootstrap hole described in §11.

---

## §4 — Promotion Ladder + Graveyard Log

Four-tier escalation from one-time miss to mechanical enforcement.

```
TIER 1 — One-time miss
  Documented in feedback memory or retrospective. No special enforcement.

TIER 2 — Recurrence (2nd time)
  Add to triggers.py. Hook surfaces reminder when keyword appears
  in prompt or my tool args.

TIER 3 — Persistent recurrence (3rd time, or recurs despite trigger)
  Promote to refresher.md slot. Session-start injection ensures
  pattern is in mind for every session, not just keyword-triggered.

TIER 4 — Trigger + refresher both insufficient
  Promote to MECHANICAL ENFORCEMENT:
  - Binary-checkable? → automated guard (pre-commit hook / CI test /
    PreToolUse hook that BLOCKS, not just warns)
  - Judgment-required? → preflight-drafting-checklist hard-gate
    (preflight cannot pass until question is explicitly answered
    in writing — not just reviewed)
```

**Promotion criteria:** A refresher slot earns Tier 4 promotion when:
- Recurred 3+ times across 2+ sprints AND
- Either (a) binary-checkable → pre-commit/CI hook eligible, OR
  (b) reduces to a single question that can be added to
  preflight-drafting-checklist

**Promotion timing:** **Implement in the same sprint-close commit.**
Don't defer. If a pattern earned promotion, fix the cause now. The
Tier 4 work is bounded by criteria (binary-checkable or reducible) so
the commit stays small.

**Graveyard log: `docs/discipline_graveyard.md`** — append-only.
Logged at every Tier 4 promotion. Schema:

```markdown
## <YYYY-MM-DD> — <pattern name>

- **Recurrence count at promotion:** N (across <sprints>)
- **Mechanism:** <pre-commit hook | CI test | PreToolUse block |
  preflight-drafting-checklist Item N>
- **File:** `<.claude/hooks/foo.py | docs/templates/checklist.md>`
- **Refresher slot vacated:** yes
- **Original lesson:** `docs/lessons/<name>.md` (still authoritative)
```

This is institutional memory that prevents re-canonization or re-debate
of solved problems.

---

## §5 — Maintenance Model

| Artifact | Edited when | Edited by | Approval gate |
|----------|-------------|-----------|---------------|
| `.claude/triggers.py` | Continuously, on any caught drift | Either PM or CLI Claude | The maintainer reviews diff post-hoc (write-directly, per `feedback_durable_doc_write_directly.md`) |
| `.claude/refresher.md` | Sprint-close only, per Standing Order B | Either PM or CLI Claude (whoever drafts sprint-close addendum) | In sprint-close commit diff |
| `.claude/hooks/*.py` | Rare — only at Tier 4 promotions or bug fixes | Whichever Claude is executing the promotion | The maintainer reviews diff in sprint-close commit |
| `.claude/settings.json` (hooks section) | Rare — only when adding/removing a hook | Same as above | In sprint-close commit |
| `docs/discipline_graveyard.md` | Append-only at Tier 4 promotion events | Whichever Claude promotes | In same commit as promotion |
| `docs/templates/preflight_drafting_checklist.md` | When new judgment-required items are added | Same as above | Same as above |

**No separate schedule. Everything is event-driven:** drift caught →
triggers update. Sprint closes → refresher review. Promotion criteria
met → mechanical enforcement ships.

---

## §6 — MVP Scope (two commits within one meta-sprint)

### Commit 1 — Infrastructure

Lands the wiring; system is operational but no Tier 4 enforcement yet.

**Files created:**
- `.claude/triggers.py` — initial 16-entry MVP set (15 domain +
  `drift-correction-language` meta-trigger; §3.1 + §11.1)
- `.claude/refresher.md` — initial 5 slots (§3.2)
- `.claude/hooks/trigger_injector.py`
- `.claude/hooks/session_refresher.py`
- `docs/discipline_graveyard.md` (empty, with header explaining purpose)

**Files modified:**
- `.claude/settings.json` — register UserPromptSubmit, PreToolUse, SessionStart hooks
- `CLAUDE.md` — Standing Order additions A, B, D, E, G (§3.4). G must
  ship in Commit 1 because the sprint-close audit (Layer B of §11)
  applies from the meta-sprint's own close onward.

**Acceptance:**
- Open a new session in the project directory; SessionStart hook outputs
  refresher.md content; visible in initial context.
- Send a prompt containing "drafting preflight"; UserPromptSubmit hook
  fires; output includes `[Triggers fired: preflight-drafting]` header.
- Trigger a Bash tool call containing "git mv"; PreToolUse hook fires;
  output includes `[Triggers fired: file-archival-or-move]` header.
- Send a prompt containing "you missed X" or "we covered this before";
  UserPromptSubmit hook fires with `drift-correction-language` trigger;
  output includes the §11.1 reminder. Layer A operational from day one.

### Commit 2 — First Tier 4 promotions

Proves the loop works end-to-end.

**Promotions (all 3 meet criteria already):**
- **Check 1** → pre-commit hook (binary-checkable, 5 recurrences across
  3 sprints). New file: `.claude/hooks/precommit_check1.py`.
- **Manual pre-commit hygiene checks** → CI guard (absorbed S-2, binary-checkable). New file:
  `.claude/hooks/precommit_pii_guard.py`.
- **Broaden-without-reinventory** → preflight checklist Item 12
  (judgment-required, 6 recurrences in 2 sprints). Edit to
  `docs/templates/preflight_drafting_checklist.md`.
- **Bonus (already-pending):** Grep-count discipline → preflight
  checklist Item 11. Same edit.

**Files modified:**
- `.claude/settings.json` — register precommit hooks
- `CLAUDE.md` — Standing Order additions C, F (§3.4)
- `docs/templates/preflight_drafting_checklist.md` — Items 11 + 12
- `docs/discipline_graveyard.md` — 3 promotion entries
- `.claude/refresher.md` — vacate 3 slots (Check 1, secrets/PII,
  broaden); leave empty unless a clearly-recurring pattern from the
  22-miss inventory qualifies. The 5-slot cap is a maximum, not a
  minimum. Empty slots are fine — better than padded ones that dilute
  signal. Slots 3 (hotfix-on-hotfix) and 5 (post-tag housekeeping)
  remain populated.

**Acceptance:**
- Pre-commit hook fires on a deliberate test commit that cites an
  untracked file; commit blocked with clear error.
- Pre-commit hook fires on a deliberate test commit that introduces a
  fake API key or real-looking email; commit blocked.
- Refresher.md has 5 slots, 3 freshly backfilled from §1.2 backlog.

### Out of MVP scope (deferred to natural sprint-close events)

- Tier 4 promotion of post-tag housekeeping (judgment, awaiting first
  sprint-close to surface)
- Tier 4 promotion of hotfix-on-hotfix (awaiting next hotfix to test
  trigger)
- Domain-specific triggers beyond initial 15 (add as encountered)

---

## §7 — Open Questions for Implementation Plan

These are decisions deferred to writing-plans-skill output:

1. **Exact stdin contract** for Claude Code hooks (UserPromptSubmit
   delivers prompt as stdin string; PreToolUse delivers JSON with
   `tool_name` + `tool_input`; exact field names need verification
   against Claude Code hook documentation at implementation time).
2. **JSON output schema** for hook responses if context injection
   requires structured response (some hook types support stdout text;
   others require `{"hookSpecificOutput": {...}}` JSON).
3. **Built-in rule set** for the secrets/PII guard.
4. **Hook ordering** — if multiple hooks register on same event, what's
   the execution order? Should triggers always run first?
5. **Failure mode** — if hook script crashes, does the prompt still
   process? Need clear graceful-degradation contract so a broken hook
   doesn't brick sessions.

---

## §8 — Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Hooks become noisy (too many false-positive triggers) | Visible `[Triggers fired: X]` header lets the maintainer audit; sprint-close review trims false-positives from triggers.py |
| triggers.py grows unboundedly | No cap by design (continuous learning is the point); but sprint-close review can retire never-fired entries |
| refresher.md decays as patterns are forgotten | Standing Order B enforces sprint-close review with explicit slot management |
| Hook script bug bricks all sessions | Implementation plan must include graceful-degradation: any hook exception → log + exit 0, never block session |
| Tier 4 promotions add too much code per sprint | Criteria require "binary-checkable" or "reduces to single question" — bounds the work to small additions |
| System is itself a recurring miss (we forget to update triggers.py when drift happens) | See §11 — four-layer bootstrap closure: Layer A real-time `drift-correction-language` trigger; Layer B sprint-close hard-gated audit; Layer C cost-of-failure visibility; Layer D conditional Tier 4 promotion if A leaks. Recognized as irreducible-floor in §11.5 — full closure is impossible, but surface is minimized. |

---

## §9 — Success Criteria

**Resolution rule (per the maintainer 2026-05-22 decision):** A pattern is
considered resolved when it has gone **two consecutive sprints without
recurrence**. If it resurfaces after that, it returns to the active list
like any other recurring miss — no special treatment for previously-resolved
patterns. Resolution is provisional; recurrence is the only signal that
matters.

**System-level checks after first two full sprints (beta-2.16-meta closes,
then the following sprint runs and closes):**

- Discipline graveyard has 3+ entries (at minimum, the 3 from Commit 2).
- At least 1 trigger fire is documented in a sprint retrospective as
  having prevented a recurrence.
- Refresher.md slot churn has happened: ≥1 slot promoted, demoted, or
  added across the two sprints.
- For each of the 5 initial refresher patterns: count recurrences across
  the two sprints. A pattern with zero recurrences in both sprints is
  considered resolved and demoted out of the refresher (per Standing
  Order B). A pattern with 1+ recurrences stays; the resolution clock
  resets.

If after two sprints the recurrence rate hasn't measurably dropped vs.
the beta-2.11-2.15 baseline (average 4+ documented misses per sprint),
the design is revisited — likely Tier 4 promotion criteria are too
loose, the trigger keyword set is too narrow, or §11 layers are leaking.

---

## §10 — Next Step

After the maintainer approves this spec: invoke `writing-plans` skill (per
brainstorming workflow) to generate a per-commit implementation plan
for Commits 1 and 2. The implementation plan resolves §7 open questions
against Claude Code hook documentation, pins down the built-in
rules for the secrets/PII guard, and provides the per-file diffs
expected in each commit.

---

## §11 — Meta-Recursive Structural Hole (the system maintains itself)

**The hole:** Updating `triggers.py` when drift happens depends on me
remembering to do it. Standing Order A says "in the same turn as the
correction" — but that step has the exact failure mode (forgetting a
rule that applies) that the system is meant to prevent. Bootstrap
problem: the feedback loop's growth requires manual upkeep, and the
upkeep can itself be missed.

No system can fully close this. Four layers reduce the surface to
near-zero in steady state.

### 11.1 Layer A — Real-time auto-detection via trigger

Add `triggers.py` entry with id `drift-correction-language`:

```yaml
- id: drift-correction-language
  patterns:
    - "you (missed|forgot|didn't)"
    - "we (covered|discussed) this"
    - "as (I |we )?(said|discussed) before"
    - "this is the \\d+(st|nd|rd|th) time"
    - "again, you"
    - "I (told|asked) you"
    - "(we|I) covered"
  scope: prompt
  reminder: |
    The maintainer is correcting drift. Before responding to the substance:
    (a) Acknowledge the correction explicitly.
    (b) Check whether `.claude/triggers.py` has an entry whose
        patterns would have caught this drift if they'd been there
        a turn earlier.
    (c) If no matching entry exists, ADD ONE in this same turn,
        alongside the substantive response.
    Per Standing Order A and `feedback_meta_recursive_defect.md`.
```

This makes drift-correction itself a trigger. The system surfaces its
own maintenance need at the moment maintenance is needed.

### 11.2 Layer B — Sprint-close audit, hard-gated

Add to sprint-close addendum preflight (in
`docs/templates/preflight_template.md` or as a new section in the
addendum's own preflight):

> **Triggers Audit (hard gate — required for sprint-close addendum
> commit to land).** For every miss documented in this sprint's
> retrospective §4 (or equivalent "dead ends," "corrections," "misses
> canonized" sections), list:
> - The miss (one line)
> - The `triggers.py` entry that would have caught it (by ID)
> - If no entry caught it: "ADDED → <new entry ID>" with the entry
>   appearing in the same commit diff
> - If intentionally not adding (e.g., one-off): "NOT ADDED because
>   <reason>"
>
> Paste this table as a section of the sprint-close commit message.
> Without it, the addendum commit cannot land.

This catches whatever Layer A missed in-session. The hard gate forces
the audit; without the gate, the audit becomes optional and decays.

### 11.3 Layer C — Cost-of-failure visibility

If the system fails to maintain itself, the same drift pattern recurs.
Recurrence is visible in three places, each of which is read regularly:

- `refresher.md` recurrence counters increment
- Sprint retrospectives §4 cite the same pattern across multiple sprints
- `discipline_graveyard.md` shows nothing (no promotions happening
  → no patterns being permanently solved → system is leaking)

This isn't a fix; it's an alarm. Combined with Layers A and B, the
alarm becomes the prompt to investigate why the layers are leaking.

### 11.4 Layer D — Future Tier 4 promotion if A keeps leaking

If sprint-close audits (Layer B) keep finding in-session corrections
that Layer A didn't catch — i.e., my real-time updating is unreliable
despite the trigger — promote to a `Stop` hook (or post-tool-use hook)
that scans the prior turn for correction language and emits a forcing
prompt: "The last turn contained correction language matching pattern
X. Update triggers.py NOW before the next user turn, OR explicitly
suppress this with a reason."

This is mechanical enforcement of Layer A. It's heavier (false-positive
risk: any back-and-forth has language that looks like correction) and
intrusive. Tier 4 promotion criteria: 3+ sprint-close audits where
corrections happened in-session but weren't logged via Layer A.

Until criteria met, Layer A + B + C are the operating mechanism. Layer
D is queued.

### 11.5 What this still can't catch

A drift happens, neither the maintainer nor I notice it, it goes unmentioned in
any document. No layer catches this. The system has no way to detect
what no one identifies.

**Mitigation:** When post-hoc analysis (audit, retrospective, external
code review, an investigation prompted by something else) surfaces such
a previously-unflagged drift, it becomes a new known pattern. Layer A
then catches the *next* occurrence. The first instance is irreducible;
subsequent instances are caught.

This is the structural floor. We cannot close it further with the
system as designed. Closing it would require external surveillance
(another agent reviewing my work for drift I didn't acknowledge),
which is out of scope for this design and arguably worse than the
floor it's trying to lift.

### 11.6 Bootstrap order

For the system to come online safely:

1. **Commit 1 ships first.** triggers.py has the `drift-correction-language`
   entry from day one — Layer A is operational at session start.
2. **First sprint after Commit 1 close.** Sprint-close audit (Layer B)
   runs for the first time at the close of beta-2.16-meta itself.
   The audit covers all misses from the sprint, including any caught
   by Layer A (the trigger fired, I added the entry, audit confirms)
   and any not caught (audit adds them retroactively).
3. **Cost-of-failure alarms (Layer C)** are passive; they're visible
   from sprint 2 onward as recurrence data accumulates.
4. **Layer D promotion** is conditional and not implemented in MVP.
   Hold until Layer A leakage justifies it.
