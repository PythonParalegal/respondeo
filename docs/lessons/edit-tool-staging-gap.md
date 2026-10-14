# Edit-tool staging gap

## One-sentence summary

The `Edit` and `Write` tools modify working-tree files but do not stage them for commit; only `git mv` and `git add` stage atomically — pre-commit verification must scan `git status --short` for unstaged-modified entries before `git commit` fires.

## The pattern

Three classes of file mutation in a typical execution sequence:

1. **`git mv <src> <dst>`** — stages the rename atomically. Output of `git status --short` is `R  src -> dst`. Safe.
2. **`Write <new-path>`** — creates a new file, but the file is **untracked** until `git add` runs. Output of `git status --short` is `?? path`. A forgotten `git add` means the file is not in the commit.
3. **`Edit <existing-tracked-path>`** — modifies the tracked file, but the modification is **unstaged** until `git add` runs. Output of `git status --short` is ` M path` (leading space, then `M`). A forgotten `git add` means the modification is not in the commit even though the file itself is tracked.

The visual signal in `git status --short` is the **two-character status prefix**:

| Prefix | Meaning | Action needed |
|---|---|---|
| `M ` | Modified, staged | None |
| ` M` | Modified, working-tree only | `git add` |
| `MM` | Staged AND further-modified in working tree | `git add` to update staging |
| `A ` | Added (new file, staged) | None |
| `??` | Untracked (new file, unstaged) | `git add` |
| `R ` | Renamed, staged | None |
| `D ` | Deleted, staged | None |
| ` D` | Deleted, working-tree only | `git add` (or `git rm` for tracked) |

The failure mode is reading leading-space-`M` lines as "I see my edits, good" rather than "these aren't in the commit yet."

## Concrete example

Beta-2.14 Commit 1 (sprint-close addendum) execution, Phase 11 status check before `git commit`:

```
$ git status --short
R  docs/audits/commit_1_flag_20_insert_or_ignore_preflight.md -> docs/archive/audits/beta-2.13/...
R  docs/audits/commit_1_flag_20_insert_or_ignore_check_v1.md -> ...
R  docs/audits/commit_1_flag_20_insert_or_ignore_check_v2.md -> ...
A  docs/archive/audits/beta-2.13/commit_1_beta213_sprint_close_addendum_preflight.md
A  docs/archive/audits/beta-2.13/commit_1_beta213_sprint_close_addendum_check_v1.md
A  docs/archive/audits/beta-2.13/commit_1_beta213_sprint_close_addendum_check_v2.md
A  docs/retrospectives/beta-2.13.md
?? docs/archive/audits/beta-2.13/README.md       ← Tier README written but not staged
 M CHANGELOG.md                                   ← Edited, not staged
 M CLAUDE.md                                      ← Edited, not staged
 M docs/FLAG_REGISTRY.md                          ← Edited, not staged
 M docs/retrospectives/README.md                  ← Edited, not staged
```

Seven files staged correctly (3 renames + 4 added — the retrospective, the self-archived addendum preflight, and both self-archived addendum check reports). Five files (1 untracked `Write` output + 4 unstaged `Edit` outputs) were not in the staging area when the first `git commit` ran. The atomic-commit unit was violated. Recovery via `git commit --amend` after explicit maintainer authorization restored the intended commit shape, but the original commit had to be amended before push. On a public-repo / multi-author flow, the recovery cost would have been significantly higher (force-push to a shared remote rewriting history other contributors had pulled).

## How to apply

**Pre-commit verification (mandatory before every `git commit`):**

1. Run `git status --short`.
2. Scan column 1 (the index/staged status). Every entry should be one of `M`, `A`, `R`, `D` (capital, non-space) — meaning staged.
3. Any line with column 1 = space (` M`, ` D`) is **unstaged**. Either `git add` it or `git restore` it.
4. Any line starting with `??` is **untracked**. Either `git add` it (if intended for the commit) or leave it (if intentionally out-of-scope; e.g. local debug files in `_scratchpad/`).
5. Re-run `git status --short`. Confirm zero leading-space-`M` and zero unintended `??` entries before `git commit` fires.

**Alternative single-command check:** `git diff --name-only` (working-tree-vs-index diff) returns empty when everything modified is staged. Non-empty means something was edited but not added.

**Inline-staging discipline (preferred when feasible):** after every `Edit` or `Write` operation that produces content intended for the current commit, immediately follow with `git add <path>`. This eliminates the gap entirely instead of relying on a pre-commit scan.

**`git mv` exception:** the only tool that stages atomically. When using `git mv`, no follow-up `git add` is needed for the rename itself (though edits to the moved file's content still require `git add`).

**`git commit -a` is not a substitute.** The `-a` flag auto-stages tracked-file modifications but NOT untracked files. Relying on `-a` masks the untracked-file class of failure (case 2 in The Pattern), which is exactly the class that hit beta-2.14 C1's tier README. Use the explicit pre-commit verification instead.

## See also

- `docs/lessons/not-in-git-tracked-not-existent.md` — adjacent lesson on the **tracked vs. existent** distinction (different failure mode: file exists on disk but is not in git's index because `git add` never ran). The two lessons together cover the pre-commit class of git-state self-owns.
- `docs/lessons/atomic-multi-table-writes.md` — the data-tier analogue: an atomic unit of state change either lands all-or-nothing. Same principle applied to commit boundaries.
- `docs/lessons/chain-of-moves-stale-refs.md` — multi-commit-arc execution discipline; same family (execution-tier hygiene around git operations).
