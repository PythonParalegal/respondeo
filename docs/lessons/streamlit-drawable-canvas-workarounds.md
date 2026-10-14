# streamlit-drawable-canvas Workarounds

**One-sentence summary:** `streamlit-drawable-canvas` is unmaintained upstream and requires three coordinated workarounds — a post-install patch, a "Load Redaction Canvas" checkbox that forces an extra rerun, and a per-document/per-page canvas key to force re-mount on switch — and the three must stay in sync.

## The pattern

Depending on an unmaintained upstream library is a compromise, not a choice. Once the decision is made to keep the dependency rather than rewrite the feature that uses it, the project takes on the burden of working around the upstream defects. Those workarounds are fragile: each one addresses a specific bug, each one depends on the others, and any one removed or modified in isolation tends to re-surface the original bug.

The three workarounds for `streamlit-drawable-canvas` in this project:

1. **Post-install patch.** After every `pip install` (fresh install, upgrade, requirements change), run the documented patch script. The patch modifies the installed canvas module to fix upstream issues that block the project's use case. Skipping the patch means the canvas silently misbehaves in ways that only show up during active drawing, making the failure hard to trace back to the missed patch step.

2. **"Load Redaction Canvas" checkbox.** The canvas's `background_image` prop does not render on first mount — a known upstream bug. Streamlit's widget lifecycle requires an additional rerun after the canvas mounts for the background to paint. A UI checkbox (`🖊️ Load Redaction Canvas`) provides that second rerun by toggling a state variable the canvas wrapper watches. Without the checkbox, reviewers see a blank canvas and cannot tell whether the document failed to load or the feature is broken.

3. **Per-document/per-page canvas key.** Streamlit widgets are keyed; when the key is stable across reruns, the widget is reused. The canvas's internal state (stored strokes) survives reuse, so switching documents or pages without changing the key leaves the previous document's strokes visible on the new document's canvas. The fix: construct the canvas key as `{control_number}_{page_index}`, so any document or page switch produces a fresh key and the canvas re-mounts with empty state.

The three workarounds are load-bearing together. The patch fixes upstream bugs that make rendering work at all. The checkbox forces the background to paint. The key forces per-document isolation. If any one is removed, one of the three related bugs resurfaces, and the bug is harder to trace than a natively-correct library because the known-good configuration is a specific combination of workarounds, not a default behavior.

## Concrete example

**Source:** `AGENTS.md` Known Constraints, item 1:

> `streamlit-drawable-canvas` is unmaintained upstream. A manual patch is applied after every pip install. The canvas `background_image` also does not render on first mount — a `🖊️ Load Redaction Canvas` checkbox triggers the extra rerun needed. Canvas key includes `{control_number}_{page_index}` to force re-mount on document/page change.

The three workarounds touch three different files:

- `_scratchpad/post_install_patch.py` — the patch script, run after `pip install`.
- `pages/4_Review.py` — the `🖊️ Load Redaction Canvas` checkbox in the Redact tab.
- `pages/4_Review.py` — the canvas key construction (keyed per control_number + page_index).

In development, touching any one of these without considering the others is the specific failure pattern that has produced hard-to-reproduce canvas bugs multiple times. "I removed the checkbox because it felt redundant" (first-mount background fails). "I simplified the canvas key" (cross-document stroke leak). "I skipped the post-install patch during a quick upgrade" (upstream bug resurfaces).

## How to apply

- Before modifying any of the three workarounds, read this lesson and the others it depends on. Never change one in isolation.
- After any `pip install` that touches canvas or its deps, run the post-install patch. Confirm with a smoke test that draws a box and sees the background image behind it.
- When a canvas interaction feels broken, check which of the three workarounds might be implicated. If the background is missing, the checkbox or the patch. If a previous document's strokes are bleeding, the key.
- If the project ever migrates away from `streamlit-drawable-canvas` (to a custom React component, per `zero-risk-data-layer-rollback.md` the `RedactionViewer` effort), the three workarounds become obsolete simultaneously. Do not attempt to remove them incrementally while the library is still in use.
- Keep `_scratchpad/post_install_patch.py` up to date with the current deployment state. A stale patch is worse than no patch because developers run it expecting it to work.

## See also

- **Related lessons:** `docs/lessons/fragment-scope-rule.md`
- **Source:** `AGENTS.md` Known Constraints item 1
- **Relevant code:** `_scratchpad/post_install_patch.py`, `pages/4_Review.py` Redact tab (checkbox + canvas key construction)
