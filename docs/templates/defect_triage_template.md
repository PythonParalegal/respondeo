# Defect Triage Template

**Purpose:** Structured triage for a defect discovered during a sprint but
deferred to a later commit. The template separates *diagnosis* from *fix*
so that reviewer triage happens against evidence, not under time pressure.

**When to reach for this template:**
- A failing test / manual-verification step reveals a defect.
- The defect's scope is unclear (local symptom vs. underlying
  data-integrity violation).
- The current commit should not absorb the fix (scope-expansion probe
  failed — see `docs/lessons/scope-expansion-probe.md`).

**When NOT to reach for this template:**
- Defects with an obvious, localized one-line fix — just fix them.
- Defects that are in scope for the current commit — fix them inline,
  don't defer.

**Output produced:** a filled-in triage file at
`_scratchpad/<defect>_<date>.md` (scratchpad during active triage) or
`docs/audits/commit_NN_<defect>_preflight.md` (promoted once the fix commit
is scheduled).

**Output discipline:** This template produces **triage, not fixes**. Every
instance should carry the line "Do NOT implement without reviewer triage"
near the top of §5.

---

## §1 — Observed failure mode

What the user saw, what the error said, where it manifested. Capture:
the exception class and message (or silent-failure symptom); the user
action that produced it; the file and line from the traceback; whether the
failure is deterministic or intermittent. Repro steps are load-bearing —
a defect without repro steps cannot be verified fixed.

---

## §2 — Failing code — exact shape

Quote the offending lines verbatim. Do not paraphrase.

State:
- The **invariant the code assumes** (one sentence).
- The **condition under which the invariant fails** (one sentence).

A reader should be able to spot the defect from the quoted code + the two
sentences without opening the file.

---

## §3 — Upstream data flow

Trace the affected data from its origin (ingestion, user input, DB read)
through every function and module until the failure point — per the Iron
Law Pre-Fix Investigation Protocol in CLAUDE.md. For each step: function /
module name, what it does to the data, and whether it preserves or violates
the invariant named in §2. The function that first violates the invariant
is the true defect site, often far upstream from where the exception fires.

---

## §4 — The underlying data-integrity question

**This section is the gate.** Fix proposals do not proceed until these
questions are answered.

Frame as numbered diagnostic questions:

1. **Schema check:** does the relevant table have a UNIQUE/NOT NULL/CHECK
   constraint on the field(s) the invariant depends on? If yes → the
   failure indicates a bypass of the constraint (a separate defect). If no
   → the invariant is undefended at the schema layer.

2. **Ingestion audit:** are there ingestion paths that assign the affected
   data without enforcing the invariant? Grep the candidates explicitly.

3. **Test-data check:** run a query against the affected case that would
   surface the invariant violation. If the "known-good" regression case
   exhibits the violation, the ingestion path produced it.

4. **Cross-case audit:** if the schema lacks the constraint, run the query
   against every active case to estimate blast radius. One case affected
   → targeted data repair. Multiple cases → schema-layer fix required.

The pattern: **is the failure a symptom of bad data, a bad invariant, or
a bad assumption?** Answer that before proposing a fix.

---

## §5 — Candidate remediation paths

**Do NOT implement without reviewer triage.**

Present options A–D, typically mapping to layers. Each gets pros, cons, and
a sentence on what it does and does not cover.

- **A — Defensive in the failing code (local symptom relief).** Shortest
  change. Localized, easy rollback; but masks the underlying data condition
  and does nothing for other code paths that depend on the same invariant.
- **B — Schema-layer enforcement (structural).** Add the missing constraint
  via idempotent migration with a backfill strategy. Defends the invariant
  at the source of truth; riskier migration and needs a data-repair path.
- **C — Layered defense (both).** Schema constraint + failing-code
  resilience. Schema is the primary defense; the code hardens as a safety
  net.
- **D — Upstream fix only.** If the audit finds one specific ingestion path
  at fault, fix that path and data-repair existing violations. Surgical;
  assumes a single cause and doesn't protect against future ingestion-path
  bugs.

---

## §6 — Verified in advance

Evidence the triage has already produced, so the eventual fix commit's
preflight does not re-run it. Numbered items: byte-identity checks (the
defect predates the recent refactor), grep counts (two call sites, not a
broader pattern), ruled-out suspects (functions that look related but are
not in the data flow), boundary conditions tested (which inputs trigger
the defect and which do not).

---

## §7 — Unblocker for current work

Optional. Include only when the triage is done in parallel with unrelated
active work that the defect blocks.

If the defect blocks verification of another commit, name a workaround that
lets the other commit proceed (e.g., "avoid <path> until the fix lands,
which still exercises the commit's thesis against clean control-flow
paths"). State explicitly what the workaround does and does not cover.

---

## §8 — Provenance

Four fields:

- **Diagnosed:** date (YYYY-MM-DD).
- **Commit hash:** the branch HEAD at the time of diagnosis.
- **Verification status:** what was passing and what was deferred at that
  point in time.
- **Related memory / lessons:** pointers to any lesson or memory file that
  informs the triage (e.g., bundling-principle criteria that gate whether
  this defect belongs in the current commit).

---

## See worked example

`docs/archive/sprints/beta-2.10/sort_path_vulnerability_2026-04-17.md` —
the originating source for this template. Discovered during beta-2.10
Commit 7 manual verification when a non-default sort mode raised
`InvalidIndexError`. Triaged as pre-existing data-integrity exposure
(duplicate `control_number` values surviving dedup), deferred to Commit
7.5. The template generalizes the 8-section structure.

## See also

- `CLAUDE.md` — Standing Orders: Pre-Fix Investigation Protocol (the source
  of §3 Upstream data flow).
- `docs/lessons/scope-expansion-probe.md` — the three-criteria test that
  gates whether a defect belongs in the current commit or a deferred one.
- `docs/templates/preflight_template.md` — the next step once the triage
  produces a fix-commit scope.
