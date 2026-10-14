# Design — Near-Dupe Cluster Review (S-1b)

**Status:** DESIGN (brainstormed 2026-05-24, awaiting plan)
**Sprint:** beta-2.16, Phase 3 S-1 arc — this is the planned **C8** work (S-1b).
**Origin:** Flag #22 follow-on. S-1a (C6) fixed the near-dupe *algorithm* (k-gram shingling). S-1b adds the *human review surface* so reviewers can inspect clusters, confirm true duplicates, and rescue materially-distinct siblings that the algorithm grouped (the template-invoice case).
**Author:** PM Claude (brainstorming session with the maintainer).
**Related:** `docs/archive/specs/neardupe_false_positive_sensitivity.md` (the forward-looking Phase A–D scaffold this realizes); S-1c defensibility report depends on this design's attestation records.

---

## 1. Problem

Near-dupe analytics tags non-principal documents `NearDupe-Suppressed`, which hides
them from the default review grid. When the cluster is a true near-dupe (FW/RE
email copies) this saves review time correctly. When members share only a
*template* but differ in *material content* (invoices: same layout, different
invoice #, date, amount), suppression can drop a distinct responsive record from
review — the Flag #22 false-positive.

S-1b gives reviewers a surface to (a) see each near-dupe group, (b) inspect every
member against the principal via a side-by-side diff, (c) confirm true duplicates
or rescue distinct siblings, and (d) attest the group — producing a defensible,
court-ready record of every suppression decision.

## 2. Recon findings that shape the design

Established by reading the current code (2026-05-24):

1. **Cluster membership is not persisted.** `run_near_dupe()` writes clusters only
   to `st.session_state['nd_clusters']` (`3_Analytics.py:409`). The Execute step
   applies flat `NearDupe-Principal` / `NearDupe-Suppressed` tags but stores **no
   mapping** of which suppressed sibling belongs to which principal. After the run
   session ends, the cluster structure is gone. `get_near_dupe_cluster_detail()`
   (`db_manager.py:4318`) groups by the **family** `group_id`, which near-dupe
   never writes — so it does *not* reconstruct similarity clusters. **Persisting
   cluster membership at Execute time is the central new requirement.**

2. **Suppression's real effect is review-grid visibility, not a production filter.**
   The review grid hides `*Suppressed*` docs by default (`4_Review.py:2556`) behind
   a "Show Suppressed Items" checkbox (default off). `5_Production.py` does **not**
   filter on `NearDupe-Suppressed`. Data-reduction stats and the defensibility
   report count it.

3. **Exact dedup is a separate, hash-based mechanism.** MD5/content duplicates are
   tracked via the `processing_status` column (`'Duplicate (MD5)'`,
   `'Duplicate (Content)'`, `'Master'`; `db_manager.py:3139`, `3281`), set at
   processing time by hash equality — **not** via the `tags` column. The grid
   excludes them via `processing_status IN ('Processed','Master')`, orthogonal to
   the `%Suppressed%` filter. **S-1b touches only the near-dupe path.**

4. **The proven master/detail pattern already exists.** `4_Review.py:3014` runs
   `st.dataframe(..., on_select="rerun", selection_mode="multi-row")`, and
   `@st.fragment` is in active use (`4_Review.py:4175`, `4432`). Streamlit is
   `1.55.0`. The two-pane review console is not a new fragile invention — it
   mirrors a pattern in production today.

## 3. Core model — provisional suppression via deferred tagging

**The invariant this design establishes:**

> `NearDupe-Suppressed` means *a human confirmed a fuzzy match is a true duplicate* —
> not *an algorithm guessed*.

Suppression is a **proposal until a reviewer confirms it.** Mechanically:

- **Execute ("Auto-Tag Near Dupes")** persists the clusters and applies the
  informational `NearDupe-Principal` tag to each principal — but applies **no
  `NearDupe-Suppressed` tag.** (Principal tagging is unchanged from today; only
  suppressed-tagging is deferred.)
- **`NearDupe-Suppressed` is written only when a reviewer marks a member "Same as
  principal."** A "Distinct" decision records the judgment and leaves the doc
  un-suppressed (it flows to individual review).

**Why this is the right posture (defensibility):** No document is ever withheld
from review by the algorithm alone — a reviewer confirmed every suppression. This
structurally eliminates the Flag #22 contagion risk: an unreviewed-but-distinct
sibling can never inherit the principal's disposition, because it was never
suppressed.

**Why it is cheap to build (blast radius):** Deferring *when* the tag is applied
means every existing `tags NOT LIKE '%Suppressed%'` consumer (review grid, STR
view, reduction stats, defensibility counts) works **unchanged** — an unreviewed
member simply has no tag and naturally appears in review. We avoid rewriting
cross-cutting filters (which would be a `silent-cross-module-filter-drift` hazard).

**The honest tradeoff:** "Execute" shifts semantics from *"suppress now"* to
*"stage clusters for review."* Running analytics no longer instantly reduces the
grid — reduction is *earned* by the (fast) cluster-review pass. This is correct:
you only get reduction credit for review you actually did. The Dedup Report's
near-dupe number becomes **confirmed vs. pending** rather than a single instant
count (more honest). Timing is ideal — the platform has no production deployments
(all dev), so the behavior change carries zero live-data risk.

This model also makes the originally-scoped production "hard warning" largely
moot: unreviewed clusters don't reduce anything, so nothing is wrongly excluded.
A light, non-blocking "N clusters still pending review" FYI at burn time is
sufficient; the court-facing record is S-1c.

## 4. Data model

Two new tables (normalized: cluster-grain attestation vs. member-grain decisions).
Added via the `db_manager.py` migration loop. `PRAGMA foreign_keys` is off by
default in SQLite (`sqlite-fk-off-by-default` lesson) — cascade/cleanup handled
manually in helpers, not via FK constraints.

```
near_dupe_clusters
  cluster_id      INTEGER PRIMARY KEY   -- surrogate "pin"; minted at Execute
  run_date        TEXT                  -- clustering run timestamp
  principal_cn    TEXT                  -- the cluster's principal control_number
  member_count    INTEGER
  sim_min         REAL                  -- similarity range for display
  sim_max         REAL
  review_status   TEXT                  -- 'pending' | 'approved'
  reviewed_by     TEXT                  -- attestation: who
  reviewed_at     TEXT                  -- attestation: when
  attestation_note TEXT                 -- optional reviewer note

near_dupe_cluster_members
  cluster_id            INTEGER         -- FK (manual) -> near_dupe_clusters
  member_cn             TEXT            -- this member's control_number
  is_principal          INTEGER         -- 1 for the principal row
  similarity            REAL            -- member-to-principal similarity estimate
  decision              TEXT            -- 'undecided' | 'same' | 'distinct'
  decided_by            TEXT
  decided_at            TEXT
  similarity_at_decision REAL           -- snapshot at decision time (label store)
```

`near_dupe_cluster_members` is the **structured decision log** — it captures
affirmative "same" decisions that change no tag (and thus would be invisible to
the append-only `audit_log`), drives the review-progress UI, and is the labeled
dataset a future ML refinement loop would consume (deferred — §8).

`cluster_id` is a surrogate, independent of `principal_cn`, so the principal can
be re-derived or a member promoted without disturbing the group identity (matches
the "pin" concept — the group is stable; principal is a role within it).

## 5. Components and data flow

### 5.1 `3_Analytics.py` — Execute change (Commit α)
- Keep MinHash/LSH clustering (`run_near_dupe`) unchanged.
- At "Execute: Auto-Tag Near Dupes": persist clusters via new helper
  (mint `cluster_id`, write cluster + member rows, `decision='undecided'`,
  capture per-member similarity — estimated Jaccard of each member's MinHash
  against the principal's, from the signatures already computed during the run).
  Apply `NearDupe-Principal` as today. **Do not apply `NearDupe-Suppressed`.**
- Stats display: show "confirmed (N) / pending review (M)" for near-dupe instead
  of a single instant count.

### 5.2 `4_Review.py` — Cluster Review tab (Commit β)
New tab, STR-tab style. Built incrementally with `Edit` (the file is on the
Write-truncates list). **Master/detail (layout B):**
- **Left pane:** `st.dataframe(selection_mode="single-row", on_select="rerun")` —
  columns: cluster, #docs, sim range, status badge (pending/approved). Mirrors the
  `4_Review.py:3014` pattern.
- **Right pane (`@st.fragment` for read interactions):** principal header; member
  selector; **side-by-side diff** of the selected member vs. principal
  (`difflib` word-level, both panes, changed spans highlighted), cached via
  `@st.cache_data` keyed by `(cluster_id, member_cn)`.
- **Per-member action (binary):** "Same as principal" → applies
  `NearDupe-Suppressed` + records `decision='same'`; "Distinct" → records
  `decision='distinct'`, ensures no suppressed tag. **Writes run at app scope**
  (full rerun) per `fragment-scope-rule` (app scope fits DB writes; fragment fits
  navigation) so the left list's badges/counts refresh.
- **Per-cluster action:** "Approve cluster" → records attestation
  (`review_status='approved'`, `reviewed_by/at`, optional note). The defensibility
  capstone S-1c reads. Enabled once every member has a decision (same/distinct) —
  it attests that the whole group was reviewed, not a subset.
- Decision + tag write are **atomic** (single connection/transaction;
  `atomic-multi-table-writes` lesson) so the member-table decision and the
  `documents.tags` change never drift. `log_audit` wrapped per never-raise.

### 5.3 `db_manager.py` — helpers + migration (Commit α)
New helpers (exact signatures finalized in the plan):
`persist_near_dupe_clusters`, `get_near_dupe_clusters`, `get_cluster_members`,
`record_member_decision`, `approve_cluster`, `clear_near_dupe_clusters`.
The existing `get_near_dupe_cluster_detail` (family-`group_id` grouping — never
reconstructed real similarity clusters) is **superseded**; the Dedup Report
migrates to the new tables (Commit γ).

### 5.4 Reporting + glue (Commit γ)
- Dedup Report near-dupe cluster detail reads the new tables.
- Production: non-blocking "N clusters pending review" FYI at burn time.
- `DEPENDENCY_MAP.md`: register the two new tables and the deferred-tagging
  semantics (new cross-module surface). Tests + nav-registry reconciliation.

## 6. RBAC, closed-case, re-run

- **RBAC:** reuse the existing `tag` permission for per-member decisions
  (un-suppress/confirm *is* a tag change) and cluster attestation. Annotate gates
  with `# permission: tag`.
- **Closed case:** render the full tab with write widgets disabled + banner; reads
  stay open. No `st.stop()`.
- **Re-run policy:** re-running near-dupe re-mints clusters and orphans prior
  decisions. Re-run **clears the cluster tables + decisions behind an explicit
  warning** ("This discards N reviewer decisions across M clusters") — consistent
  with the existing "clear tags before re-run" behavior. Reviewer work is never
  silently invalidated. Re-run also clears any `NearDupe-Suppressed` tags applied
  by prior confirmations (they no longer map to a live cluster).
- **Re-run type-to-confirm guard (C8b refinement, added 2026-05-28).** If any
  reviewer decisions exist in the case (`SELECT COUNT(*) FROM near_dupe_cluster_members
  WHERE decision != 'undecided'` returns ≥ 1), the "Clear & Re-run Near-Duplicate"
  button does **not** fire on click — instead it reveals a type-to-confirm prompt
  with the current decision count surfaced explicitly. The reviewer must type the
  exact phrase `CLEAR N DECISIONS` (with the real count substituted) into an
  `st.text_input` before a final "Clear & Re-run" button enables. Wrong text → button
  stays disabled. Cancel button clears the armed state. **When the decision count
  is zero, no prompt fires** — the existing warning-and-click flow is preserved.
  Implementation reads the count via the new
  `db_manager.get_near_dupe_review_progress(case_folder)` helper (§11 / β refresh),
  which also serves the confirmed/pending metric (formerly an inline N+1 loop —
  the helper subsumes the C8a F2 inline-loop disposition now that there's a second
  caller). Rationale: a reviewer who has attested 50 clusters and discovers a
  one-cluster mistake reaches for **Re-open** (§11.5); the re-run path is reserved
  for genuine re-clustering (algorithm change, drastically different corpus) and
  the type-to-confirm guard makes the destructive scope explicit. The granular
  Re-open + the type-to-confirm guard together eliminate the catastrophic
  "force-full-rerun-to-fix-one-mistake" failure mode.

## 7. Testing

Regression tests (mirror `tests/test_neardupe_*.py` conventions):
- Execute persists clusters with **no** `NearDupe-Suppressed` tags (fail-open).
- "Same" applies the tag **and** records `decision='same'` atomically.
- "Distinct" records the decision and leaves **no** suppressed tag.
- "Approve cluster" records attestation fields.
- Re-run clears tables + decisions + prior suppressed tags.
- **Invariant pin:** exact dupes (`processing_status='Duplicate (*)'`) are
  untouched by the near-dupe path (pinned-value style, per
  `pinned-value-pattern`).

## 8. Scope boundaries — deferred ("near-dupe intelligence, future session")

Explicitly **out** of S-1b, each its own future work item:
- **Flag #30 — transitive-closure grouping.** Current grouping is anchor-based and
  can fragment a family. The fix needs a linkage policy + chaining guard +
  calibration (single-linkage closure risks runaway mega-families — worse for the
  UI than bounded anchor groups). Its own spec + F-4 calibration session. The
  `cluster_id` persistence is forward-compatible — the fix only changes how members
  are assigned, not the schema or UI.
- **Rendered-document side-by-side viewer** (two PDFs/images). Bigger lift,
  leans on the quirky server-side PDF viewer, doesn't highlight differences.
  Secondary "confirm the form" mode for later.
- **Automated double-pass classifier** ("find what differs, where, how
  consistently, how much → auto-classify same/distinct"). Reintroduces the
  "how-different-is-material" threshold problem + generality risk across doc types.
  The S-1b diff view is the *human* version and generates the ground truth a
  classifier would need.
- **ML refinement loop** (learn from logged decisions to re-tune clustering).
  Deferred to a growth-stage feature per the maintainer: ML stays boxed until the platform
  is stable — the overhead is not initial-dev work. Also carries a defensibility
  caveat (adaptive/learned suppression is harder to defend than a transparent
  threshold — Daubert exposure). S-1b only *stockpiles the labels* so this door is
  cheap to open later.

## 9. Implementation surface (for the plan)

Three files + reporting glue, ~3-commit arc (finalized by `writing-plans`):
- **Commit α** — schema (2 tables) + `db_manager` helpers + migration + Analytics
  Execute deferred-tagging + stats display.
- **Commit β** — Review Cluster Review tab (master/detail + diff + decisions +
  attestation).
- **Commit γ** — Dedup Report migration to new tables + production pending FYI +
  `DEPENDENCY_MAP` + tests + nav reconciliation.

## 10. Relationship to S-1c

S-1c (defensibility report) reads `near_dupe_clusters` + `near_dupe_cluster_members`
to produce a court-ready listing: every cluster, its principal, each member's
decision, who attested and when. S-1b's attestation records are S-1c's data source.
S-1c is a separate commit (C9) and depends on this design's persistence landing first.

---

## 11. C8b UX detail (Cluster Review tab build)

**Status:** Appended 2026-05-28 from the C8b UX brainstorming refresh, after C8a (α) landed and surfaced empirical requirements (overlap is materially active; family-preserved members need explicit treatment) that the original §5.2 sketch left under-specified. §11 supersedes §5.2's "Layout B / master/detail" notes where they conflict; the rest of §5.2 (decision atomicity, fragment scoping, never-raise audit) stands unchanged. The plan's β tasks at `docs/superpowers/plans/2026-05-25-neardupe-cluster-review.md` need a light refresh against §11 before C8b preflight; see §11.10.

### 11.1 Spatial layout — locked

Master/detail two-pane inside the Review-page tab. Streamlit uses
`layout="wide"` (verify in `home.py` / `st.set_page_config` during the preflight pre-flight check); the tab gets the full main content area (~1500px on a true widescreen, ~1200px on a 1080p laptop) and no other Review tab renders while this one is active.

**Column ratio: 18 / 82 (`st.columns([0.18, 0.82])`).** Left pane ≈ 215px on a 1200px page; right (detail) ≈ 985px. The list is trim-to-content; the diff dominates.

**Left pane (cluster list):** `st.dataframe(height=NEARDUPE_PANE_HEIGHT, on_select="rerun", selection_mode="single-row")`. Rows show `cluster_id · N docs · status badge`. **Similarity range moves to row hover** (`title=` tooltip); it isn't an at-a-glance signal worth permanent space, but a reviewer who wants it is one hover away.

**Right pane (detail), top-to-bottom (A → B → C → D — matches reviewer workflow):**

- **A — Member nav bar** (§11.2)
- **B — Diff pane** (§11.3)
- **C — Per-member action area** (§11.4)
- **D — Cluster attestation row** (§11.5)

**Two affordances for real-estate flexibility:**

- **"◀ Collapse" button on the left pane header** — collapses the list to a thin 28px strip (still clickable to expand back), giving the detail pane the full ~1180px and the diff columns reflowing to ~580px each. For deep-focus review.
- **"⤢ Expand diff" button on the diff header** — opens the diff in a full-screen modal via `st.dialog` (supported in Streamlit 1.55). For multi-page documents or dense reports where the in-tab pane isn't enough.

**Pane heights are a single spec-level constant:** `NEARDUPE_PANE_HEIGHT = 700`. Applied to both the `st.dataframe` and the diff component. Fits a 1080p viewport with browser chrome + Streamlit header + Review tab bar (~400px fixed overhead → ~680px available). On 1440p the constant bumps to ~900 in a future tuning pass; tunable in one place.

### 11.2 Member navigation widget

Horizontal row at the top of the detail pane:

```
[◀ Prev]  Member M of N  [picker selectbox] [Next ▶]
```

The picker is an `st.selectbox` showing every member with inline status icons: `INV-1042 · ✓ same` / `INV-1043 · ⏳ pending` / `INV-1044 · 🛡 family` / `INV-1045 · 🔒 decided in C-142`. Picking jumps to that member. Prev/Next are the primary affordance for sequential review; the picker is for jumping out of order.

Position counter (`Member M of N`) shows progress through the cluster. M/N counts **all** members (suppressible + family-preserved + locked); the approval gate (§11.6) uses a different denominator.

Selected member is stored in `st.session_state[f'nd_member_{cluster_id}']` (cluster-scoped so switching clusters resets to first member). Stale-selection guard: if the selected index exceeds member count after a re-run reshapes the cluster, reset to 0 — same defensive pattern as the cluster-list selection guard.

### 11.3 Diff pane

**Rendering:** `st.components.v1.html(build_side_by_side_diff_html(...), height=NEARDUPE_PANE_HEIGHT, scrolling=True)` inside an `@st.fragment` so member-nav and toggle interactions don't rerun the whole page.

**Default mode: context-collapsed.** `difflib.HtmlDiff(...).make_table(a_tokens, b_tokens, fromdesc="Principal", todesc="Member", context=True, numlines=2)` — unchanged stretches collapse to "... N unchanged lines ..." between change hunks, with 2 lines of context around each change. A 50-page contract with 5 changed paragraphs renders as 5 small hunks (~30 lines of visible text), with line numbers preserved so each change is locatable.

**"Show full text" toggle** at the top of the diff pane (next to the Expand button) — `st.toggle("Show full text", key=f"nd_full_{cluster_id}_{member_cn}")`. When on, `build_side_by_side_diff_html(...)` is called with `context=False` and the full document text renders in both columns with the changed spans still highlighted; reviewer scrolls infinitely through each column (independent scroll, sticky column headers via CSS `position:sticky; top:0`).

**"⤢ Expand diff" button** — opens an `st.dialog` modal containing the same `build_side_by_side_diff_html` output at a larger height (`height=900`) for documents that exceed the in-tab pane. The toggle state carries into the modal.

**Diff caching:** `@st.cache_data(ttl=600)` on `build_side_by_side_diff_html`, keyed by `(case_folder, cluster_id, member_cn, context_mode)`. Member text is fetched via `os_manager.get_document_content(case_folder, control_number)` (the helper added in C8b per plan task β2).

**Page-by-page navigation is explicitly NOT in scope.** The OpenSearch `_source.content` field is a concatenated text blob with no page boundaries; adding them would require re-extraction + re-indexing + schema migration touching `2_Processor.py`. Future enhancement, not C8b. The context-collapsed default makes long docs tractable without it.

**Future polish (deferred):** an `n` / `p` keyboard shortcut to jump between change hunks. Nice-to-have, requires a JS shim, defers cleanly.

### 11.4 Per-member action area — three visual states

Anchored below the diff. Which state renders depends on the selected member:

**State 1: Normal suppressible member.**
```
Decide on {member_cn}:   [✓ Same as principal]   [✗ Distinct]
```
"Same" calls `db_manager.record_member_decision(..., 'same', ...)` → applies `NearDupe-Suppressed` tag + records decision. "Distinct" calls with `'distinct'` → records decision, ensures no tag. Both writes run at app scope (full `st.rerun()` after) so the cluster list's badge refreshes.

**State 2: Family-preserved member.**
```
🛡 Family-preserved ✓   Attachment of {parent_cn} — no decision needed. Continue to next.   ⓘ
```
Amber-tinted resolved panel; **no buttons rendered at all** (not disabled — absent). Visual "done by rule" signal: green ✓ check on the title. The ⓘ on the right is a hover-only tooltip explaining the family-integrity-over-dedup rule for the curious reviewer or a future auditor. **The reviewer's next step is the "Next ▶" button at the top of the detail pane** — there's no decision to make here, the system handled it. Auto-exempt from the approval gate (§11.6).

**State 3: Overlap-locked member.** Two sub-flavors, same visual shape:

- **Decided elsewhere** — the doc was already decided "Same" or "Distinct" in another cluster:
```
🔒 Decided in Cluster {C-X}   [Same disabled] [Distinct disabled]   [↗ Open Cluster X]
```

- **Principal elsewhere** — the doc is the principal of another cluster:
```
🔒 Principal of Cluster {C-Y}   [Same disabled] [Distinct disabled]   [↗ Open Cluster Y]
```

Badge + disabled buttons (kept visible here so the reviewer sees the action shape that would have applied, but unable to fire) + a jump-to-source button. **Counts as decided for the approval gate** (§11.6) — the decision exists, it just lives elsewhere.

**No disabled-button traps anywhere on family-preserved.** Disabled-but-visible buttons cause "why isn't this firing?" confusion. Family-preserved gets a clean *resolved* panel with no buttons. Overlap-locked keeps the buttons visible because they convey *what the action would be* — but the badge + jump CTA make the lock unambiguous.

### 11.5 Cluster attestation row — three visual states

Anchored at the bottom of the detail pane (below the per-member action area). The cluster-level capstone, where the reviewer attests once all suppressible members are decided.

**State 1: PENDING** — at least one suppressible member still undecided.
```
[PENDING]   <note input disabled, placeholder = "Decide all suppressible members to enable approval…">   [✓ Approve cluster — disabled]
```
Amber-tinted row. Note input visible but disabled; its placeholder doubles as the state hint so the reviewer knows what's gating approval.

**State 2: READY** — every suppressible member has a decision.
```
[READY]   <note input live, placeholder = "Attestation note (optional)">   [✓ Approve cluster — enabled, green CTA]
```
Indigo-tinted row. Note input active; the reviewer can leave a free-text attestation note (optional) before clicking Approve.

**State 3: APPROVED** — the reviewer clicked Approve. Row transforms into an attestation record with a discoverable re-open affordance:
```
[APPROVED]   ✅ {reviewed_by}   attested {reviewed_at}      [↺ Re-open]
             Note: "{attestation_note}"  (if present, below the row)
```
Green-tinted row. The `[↺ Re-open]` button renders as a subtle secondary action (smaller, lower contrast than primary actions elsewhere — e.g., `rgba(148,163,184,0.22)` background, `#cbd5e1` text) so it doesn't invite accidental clicks but stays discoverable. **Two-click confirmation:** first click reveals "Click again to confirm re-open · [Cancel]"; second click fires. (Pattern: a `st.session_state[f'nd_reopen_armed_{cluster_id}']` flag toggled by the first click, the action runs only if the flag is set, the Cancel button or an automatic timeout clears it.)

**Re-open behavior:** confirmed click calls `db_manager.reopen_cluster(case_folder, cluster_id, username)`, which (1) snapshots the prior attestation (`reviewed_by`, `reviewed_at`, `attestation_note`) into a `NEARDUPE_CLUSTER_REOPENED` `audit_log` entry, then (2) reverts the cluster row to `review_status='pending'`, clearing `reviewed_by`/`reviewed_at`/`attestation_note`. **Member decisions are NOT cleared** — they survive the re-open. The cluster typically transitions back to **READY** (all suppressible still decided, awaiting re-approve). The reviewer can then re-click any Same/Distinct to change a single member's decision (existing `record_member_decision` handles it, including the cross-cluster fan-out from §11.7), or simply re-Approve with the same decisions plus a new note.

**Why this is the defensibly correct shape:**
- **The forensic record lives in `audit_log`, immutably.** Every Approve writes a `NEARDUPE_CLUSTER_APPROVED` entry; every Re-open writes a `NEARDUPE_CLUSTER_REOPENED` entry snapshotting the prior attestation; every member decision writes a `NEARDUPE_DECISION` entry. A court query about "what was attested on date X, by whom, with what note?" reads the audit log, which never overwrites. The cluster table reflects the *current* attestation; audit_log carries the full chain.
- **Editability of current state is consistent with the rest of the platform.** Tags, decisions, custodian assignments, hold statuses — every state surface in this app is editable with audit-log-tracked history. A "this cluster's attestation is forever frozen" semantic would be the *odd one out*, not a defensibility feature.
- **Granular re-open is what makes this usable.** A reviewer discovers a misclick after attesting 50 clusters; the cost to fix should be one cluster's worth of effort, not 50. Forcing a full Clear-and-Re-run for a one-cluster mistake is the catastrophic failure mode, not a defensibility feature.
- **Re-run still exists for the *re-clustering* case, now guarded.** "Clear & Re-run Near-Duplicate" on the Analytics tab (per C8a) discards all decisions because the clusters themselves change — old decisions can't map to new cluster membership. Re-open and Re-run are *different operations for different scenarios*: Re-open fixes a single attestation; Re-run re-derives the clusters from scratch. **Re-run is now further guarded by a type-to-confirm prompt** (`CLEAR N DECISIONS` where N is the current decision count) — see §6 for the refined policy. The guard fires only when decisions exist; an unreviewed case still re-runs with the original warning-and-click.

**Permission gate:** Re-open is gated under the same `tag` permission as the primary review actions (`# permission: tag`). Future option for stricter shops: a `reopen_neardupe` permission distinct from `tag` so manager-level review is required to un-attest; not in scope for C8b — the same-permission default is the lowest-friction path that still gates on review-class access.

**Note input always visible** (not hidden behind a "click Approve to add a note" expander). Placeholder text shifts by state. One predictable row position; no surprise modals on the way to Approve.

### 11.6 Approval gate — which members count

`Approve cluster` enables when, for the selected cluster:

```
all members where family_preserved == 0 have decision IN ('same', 'distinct')
```

- **Family-preserved members** (`family_preserved == 1`) are exempt from the denominator. Their decision field stays `'undecided'` and that's fine.
- **Suppressible members** with a local decision (`'same'` or `'distinct'`) count.
- **Overlap-locked members** count as decided — the decision was made in another cluster but the document's state is unambiguous (see §11.7 on how the decision propagates).
- **Undecided suppressible members** block approval until the reviewer Same/Distincts them.

The cluster-list badge (§11.8) renders the fraction `M/N` where `N = count(suppressible)` and `M = count(suppressible-with-decision OR overlap-locked-with-decision)`.

### 11.7 Decision propagation (per-document, not per-row)

**Schema refinement vs. C8a (α):** add `decided_in_cluster_id INTEGER` to `near_dupe_cluster_members`. NULL = undecided; equals this row's `cluster_id` = decided in this cluster; differs = decided elsewhere → lock.

**Behavior of `record_member_decision`:** when the reviewer clicks Same/Distinct in cluster X for member `cn`, the function:

1. Updates the (cluster_id=X, member_cn=cn) row's `decision`, `decided_by`, `decided_at`, `similarity_at_decision`, **and** `decided_in_cluster_id = X`.
2. **Fans the decision out** to every other (cluster_id=Y, member_cn=cn) row for the same `member_cn`: same `decision`, same `decided_by`, same `decided_at`, **but `decided_in_cluster_id = X`** (the source).
3. Applies/strips the `NearDupe-Suppressed` tag (single per-doc action, idempotent — same outcome regardless of which row triggers).
4. All in one transaction (atomic-multi-table-writes).

**Cost:** per decision, one tag write + N row updates where N = number of clusters the doc appears in. Empirically (CLI v2-check, 31 overlapping members of 388 ≈ 8%) the fan-out is small in practice.

**UI consumes `decided_in_cluster_id`:** in cluster Y's detail pane, when the selected member has `decided_in_cluster_id != Y`, render the overlap-locked panel (§11.4 State 3) with the source cluster's ID and a jump button.

### 11.8 Cluster-list badge progression — four states

The right-anchored badge on each cluster row in the left pane:

| State | Badge | Color | Meaning |
|---|---|---|---|
| Pending | `PEND` | amber (`rgba(245,158,11,0.22)` bg, `#fde68a` text) | 0 decisions on suppressible members |
| In progress | `M/N` | indigo (`rgba(99,102,241,0.22)` bg, `#c7d2fe` text) | M of N suppressible decided; M > 0, M < N |
| Ready to approve | `N/N ✓` | green-tint with border (`rgba(34,197,94,0.22)` bg, `#bbf7d0` text, green border) | all suppressible decided; awaiting Approve click |
| Approved | `APPR` | solid green (`rgba(34,197,94,0.85)` bg, `#fff` text) | attested |

The "Ready" state (full fraction with a ✓) is visually distinct from APPR so the reviewer scanning the list sees "this one's primed, click to attest" vs. "this one's done." Sim range moves to row hover (`title=` tooltip) — at-a-glance signal that survives is **doc count + status**, which is what a reviewer uses to pick what to tackle.

### 11.9 Theme-safe color discipline

Streamlit honors system dark/light themes. UI elements with hardcoded colors must work in both. **Discipline:**

- Prefer Streamlit's native `st.badge(...)` (1.55+) where the use-case fits — it auto-themes.
- For custom HTML/CSS:
  - **Light text on translucent backgrounds.** Use `#e2e8f0`, `#c7d2fe`, `#fde68a`, `#bbf7d0` (light slate / light indigo / light amber / light green) as text colors over `rgba(R,G,B,0.18–0.30)` backgrounds. These read in both themes.
  - **Never dark text on dark backgrounds.** `#4338ca` text on `rgba(99,102,241,0.18)` background — the failure mode that surfaced during the overlap-lock brainstorm — is invisible in dark mode. Avoid all dark indigos, dark slates, near-black text colors in this surface.
  - Borders: use the saturated form of the accent color (`rgba(R,G,B,0.40)`) for visual hierarchy without contrast loss.

CSS lives in a single string at the top of the tab body, kept short and named (`_ND_TAB_CSS`).

### 11.10 Plan-task implications for C8b preflight

The plan at `docs/superpowers/plans/2026-05-25-neardupe-cluster-review.md` β tasks (Commit β — the Review tab) need a light refresh against §11 before the C8b preflight is drafted. Specifically:

- **β1 — diff function:** unchanged.
- **β2 — `os_manager.get_document_content`:** unchanged.
- **β3 — Review tab:** refine step-by-step to match §11 layout/proportions, member-nav widget, three per-member states, three attestation states (incl. the **Re-open affordance + two-click confirmation** in APPROVED), four badge states, theme-safe colors, the `decided_in_cluster_id` schema delta (small migration), `record_member_decision` fan-out behavior, the new `db_manager.reopen_cluster(case_folder, cluster_id, username)` helper (with `NEARDUPE_CLUSTER_REOPENED` audit-log action snapshotting prior attestation), `NEARDUPE_PANE_HEIGHT` constant, and the Expand-modal `st.dialog` integration.
- **β-Analytics — re-run type-to-confirm guard:** modify the existing "Clear & Re-run Near-Duplicate" handler in `pages/3_Analytics.py` (C8a-landed at L628–643 against pre-Phase-B HEAD; CLI re-locates by stem) to read decision count via the new `db_manager.get_near_dupe_review_progress(case_folder)` helper and gate the destructive click behind a type-to-confirm `st.text_input` requiring the exact phrase `CLEAR N DECISIONS`. Helper returns `{confirmed, pending, n_decisions, n_clusters}` and replaces the dispositioned-but-now-needed F2 inline metric loop in the Execute path. Add the helper alongside the other db_manager neardupe-cluster helpers (after `clear_near_dupe_clusters`).

The C8b preflight pulls these into per-section discipline (extraction inventory, signature proposals for the new helper boundaries, scope-expansion probes for the `decided_in_cluster_id` migration, etc.). Per the project's PM→CLI workflow, the preflight is the next planning artifact — not a fresh `writing-plans` invocation; the existing plan's strategic skeleton stands and is amended in place when β lands.

### 11.11 What §11 does NOT change

- Persistence (§4 two-table model) — schema gains one column (`decided_in_cluster_id`), otherwise unchanged.
- Deferred-tagging core model (§3) — provisional suppression invariant intact.
- Re-run policy (§6) — coarse, clears everything, behind a warning.
- Closed-case handling (§6) — read-only banner, write widgets disabled.
- Deferred bucket (§8) — Flag #30 transitive-merge, rendered-doc side-by-side, automated classifier, ML loop all stay deferred.
- C8a (α) — already; unaffected.
