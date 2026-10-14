# N-Stage Gate — Revision Handling

## One-sentence summary

A patched preflight is a new preflight; every PM revision requires a
fresh delta-scoped CLI pre-flight check before Stage 2 greenlight
opens, and patch + greenlight never ship in the same message.

## The pattern

The PM–CLI collaboration model is commonly described as a two-stage
gate: Stage 1 (plan approval — the maintainer reviews the preflight) and
Stage 2 (execution approval — CLI reports on their pre-flight check
pass and the maintainer greenlights execution). This description is accurate
when the preflight passes CLI's initial check cleanly. It is
**incomplete** for the more common case where CLI's pre-flight check
flags something and PM revises the preflight.

The correct model is N-stage: every PM patch in response to a CLI flag
adds a gate. The flow is:

```
PM drafts preflight v1
  ↓
Stage 1: PM sends to the maintainer → plan approval
  ↓
Pre-flight check 1: CLI reads v1, runs checks, reports
  ↓
PM reviews CLI's report
  ↓
If CLI flags something:
  PM patches → preflight v2
    ↓
  PM sends revised preflight back to CLI — "Stage 2 remains pending"
    ↓
  Pre-flight check 2: CLI reads v2, runs delta-scoped checks, reports
    ↓
  PM reviews → repeat if needed
  ↓
Stage 2: The maintainer issues execution greenlight in a separate message
  (only after latest CLI report is clean; PM does not issue Stage 2)
  ↓
CLI executes, runs §5 verification suite, reports post-execution
```

Every PM patch adds a gate rather than collapsing one.

## Concrete example

Beta-2.11 Commit 8 execution. CLI's pre-flight check on the preflight's
initial draft flagged a factual error — Check 1 of the template listed
`license.key` and `license_cache.enc` as "canonical gitignored paths in
Respondeo" but those files don't exist yet (they're from the unshipped
license system spec). CLI presented two options: (a) accept as drafted
and fix-forward, (b) patch the spec before extraction.

PM chose (b), patched the spec, and — in the same message — issued
Stage 2 greenlight: "Structural properties you verified are unchanged...
STAGE 2 (execution approval) GRANTED. Proceed with the six operations."

The maintainer caught the pattern-level miss. The patch-plus-greenlight
collapse bypasses the gate's purpose. The gate exists because PM reasons
about the artifact and CLI verifies against the execution environment.
PM's "the predictions still hold" is a reasoning claim; CLI's grep-count
against the actually-patched file is evidence. Those are categorically
different and shouldn't be collapsed.

The §5 verification suite CLI runs post-execution caught the structural
layer of the patch by luck — it was designed against the original
draft's expected state, and the patch didn't break structural
assumptions. The scope-expansion semantic correctness of the revision
had no scheduled check.

## How to apply

**When PM receives a CLI pre-flight check flag:**

1. Pick the resolution (option a / b / other).
2. If option (b) or any revision: patch the preflight.
3. **Send the revised preflight back to CLI with explicit delta-check
   scope** and the phrase "Stage 2 remains pending." Do NOT include any
   greenlight language — Stage 2 is the maintainer's to issue, not PM's.
4. CLI runs a delta-scoped check on the patched content, reports in the
   CLI tab.
5. The maintainer reads CLI's report; if clean, the maintainer issues Stage 2 greenlight
   in a separate message. If not clean, PM iterates from step 2.

**Delta-check scope** is typically:

1. Structural verification on the patched content (re-run affected
   grep counts, re-verify markers if the patch touched anything in an
   extraction range).
2. Scope-expansion second opinion on the new text (look for new factual
   claims, new file enumerations, new paths).
3. Grep-count predictions affected by the patch.
4. Confirm the fix actually addresses the original flag.

Everything CLI already verified and PM did not touch stays verified.
Don't re-run the full pre-flight pass each round.

**PM response skeleton** for sending a revision:

```
Patch applied to <path> — [one-line description of change].

STAGE 2 (execution approval) REMAINS PENDING — the maintainer will issue in a
separate message after your delta-check reports clean.

Please run a delta-scoped pre-flight check:
  1. [specific structural check the patch could affect]
  2. Scope-expansion second opinion on the revised text
  3. Re-predict grep counts if the patched content changes §5 expectations
  4. Confirm the fix resolves the original flag

Report back in the CLI tab so the maintainer can relay to the PM tab; the
Stage 2 greenlight depends on your clean report.
```

## Why this is worth canonizing

The failure mode is PM cognitive — the temptation to collapse patch +
greenlight into one message is natural and happens quietly. The
scenarios where the gate matters most are precisely the ones where PM
feels confident the patch is small / contained / structurally safe.
That confidence is the exact failure mode the gate was built to catch
(PM-Commit-7's gitignore miss was produced by the same pattern of
confidence).

## See also

- `docs/templates/pm_cli_collaboration_workflow.md` §5 — the durable
  workflow documentation that encodes this doctrine.
- `docs/templates/preflight_drafting_checklist.md` Check 10 preamble —
  references this doctrine for drafting discipline.
- `CLAUDE.md` Standing Order: "N-Stage Gate Revision-Handling Doctrine"
  — always-injected rule requiring fresh delta-checks on revisions.
- User auto-memory `feedback_revision_requires_fresh_gate.md` — the
  PM-side behavioral reminder that the temptation to shortcut is
  itself the tell.
