# Not-in-Git — Tracked Is Not Existent

## One-sentence summary

A file being on disk is not evidence that git tracks it; use
`git ls-files <path>` to verify tracked status before prescribing
`git mv` or `git add` — gitignored files and untracked-but-existing
files share the same recovery pattern (`mv + git add`) but are distinct
root causes.

## The pattern

Files on disk can be in three states relative to git:

1. **Tracked** — `git ls-files <path>` returns the path. `git mv` works.
   `git add` just stages modifications.
2. **Gitignored** — `.gitignore` has a rule matching the path. `git
   check-ignore <path>` returns the path. `git mv` fails. `git add`
   fails (silently, with a warning).
3. **Untracked-but-existing** — the file exists on disk but was never
   `git add`'d. `git ls-files` returns empty; `git check-ignore`
   returns empty (it's not ignored, just not added yet). `git mv`
   fails with `fatal: not under version control`. `git add` works to
   introduce the file.

Packet-draft discipline often treats "the file exists" as equivalent
to "the file is tracked." This conflation is the failure mode. It
produces wrong git-op prescriptions in two distinct scenarios:

**Scenario A — Gitignored sources.** Packet prescribes `git mv` on a
file in a gitignored directory (e.g., `_scratchpad/` in Respondeo).
Fails at execution.

**Scenario B — Untracked-but-existing sources.** Packet prescribes
`git mv` on a file drafted in-session (e.g., a spec the PM just wrote).
The file exists on disk — PM verified by `ls` or `cat`. But it was
never committed. Fails at execution.

Both scenarios share the same recovery pattern: plain `mv <source>
<dest>` followed by `git add <dest>`. Git history is not preserved
(git sees the destination as a new file). This is acceptable because
neither source had git history to preserve anyway.

## Concrete example

Beta-2.11 Commit 6e.1 exercised Scenario A. The packet
moved 8 specs from `_scratchpad/` to `docs/specs/`. The packet
originally prescribed `git mv`. CLI correctly caught that `_scratchpad/`
is gitignored; `git mv` would fail. Recovery: `mv + git add`.

Beta-2.11 Commit 8 exercised Scenario B. The packet
prescribed `git mv docs/specs/preflight_drafting_checklist_spec.md
docs/archive/specs/preflight_drafting_checklist_spec.md` and asserted
"Both paths are tracked." The spec had been drafted earlier in the
current session and never committed. `git mv` failed with `fatal: not
under version control`. Recovery: same `mv + git add` pattern.

The in-session drafted file is the more insidious case because PM's
confidence that it's tracked comes from having just written it —
"I just made this file, of course it exists" — without realizing
existence and trackedness are independent.

## How to apply

**At packet-draft time**, for every file that appears in a git
operation (`git mv`, `git add`, signature section, staging list):

1. **Check TRACKED status, not just existence.**
   - `git ls-files <path>` — returns path if tracked, empty if not.
     Authoritative.
   - `git check-ignore <path>` — returns path if gitignored, empty if
     not. Useful for distinguishing gitignored from untracked-but-
     existing.
   - `git status <path>` — shows untracked files explicitly in the
     "Untracked files" section.

2. **If not-in-git (either case), reroute the operation.**
   - For a move: `mv <source> <dest>` then `git add <dest>`. Note in
     the packet that history preservation is forfeit.
   - For a stage: pair with the tracked template if one exists (e.g.,
     `config.example.py` for `config.py`), stage the template, apply
     the same edit to the untracked file as an on-disk operation,
     call out the dual application explicitly.

3. **Especially check files drafted in the current session.** These
   are the most common self-own because existence feels like proof of
   trackedness.

4. **Document the reroute in the packet.** Don't leave CLI to
   improvise the correct git operation mid-execution.

## Why this is worth canonizing

The failure mode is silent at draft time — nothing stops PM from
writing `git mv` in a prescription. It only surfaces at execution. CLI
can recover (the pattern is well-known now) but every recovery
episode is one more reason to add the `git ls-files` check to the
draft-time discipline.

This lesson also supports the preflight-drafting checklist's Check 1
(which enforces this at draft time) and the broader discipline of
"verify before you prescribe."

## See also

- `docs/templates/preflight_drafting_checklist.md` Check 1 — the
  operational checklist item that runs this verification at draft time.
- User auto-memory `feedback_gitignore_awareness_in_packets.md` (now
  titled "Not-in-git awareness") — the PM-side behavioral reminder
  covering both scenarios.
- Commit messages for Commit 6e.1 and Commit 8
  — the two worked examples in commit history.
