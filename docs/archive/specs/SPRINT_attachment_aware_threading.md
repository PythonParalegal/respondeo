# Sprint Spec: Attachment-Aware Thread Suppression

## Problem Statement

When email threading runs (`3_Analytics.py → run_threading()`), it classifies emails as either **Inclusive** (last in thread chain, keep for review) or **Thread-Suppressed** (redundant, skip). The suppression tag then **propagates to all child attachments** of suppressed emails (lines 473-490).

This means: if the original email in a thread carries attachments, and a later reply becomes the thread-principal, the original email gets suppressed — and its attachments are suppressed with it. Those attachments become orphaned. They exist in the DB but are invisible in production because both they and their parent are tagged `Thread-Suppressed`.

## Solution: Un-suppress Attachment-Bearing Emails

**Rule:** After the threading algorithm classifies emails into inclusive vs. suppressed lists, perform a second pass. Any email in the suppressed list that has child documents (attachments) in the `documents` table gets moved to the inclusive list instead.

**Tag:** These promoted emails receive the tag `Inclusive` (same as other inclusive emails). Add a secondary informational tag `Inclusive-Attachments` so reviewers can see WHY it was un-suppressed. This tag is cosmetic/informational — it does not affect any filtering logic.

**Scope:** ALL attachment-bearing emails are un-suppressed, regardless of whether the attachments are unique or duplicated elsewhere. No uniqueness checks. Conservative and defensible.

## Implementation Details

### File: `pages/3_Analytics.py`

#### Change 1: Add attachment-bearing promotion pass in `run_threading()` (after line 262, before line 263)

After BOTH the graph-based classification (lines 219-230) and the subject-line fallback (lines 232-261) have finished building `inclusive_docs` and `suppressed_docs`, but BEFORE storing them in session state (line 263), insert a new phase:

```
# ── Phase A5: Un-suppress emails that carry attachments ──────────────
# Emails with child documents (attachments) must not be suppressed,
# because suppression propagates to children and orphans the attachments.
# Move any attachment-bearing email from suppressed → inclusive.
if suppressed_docs:
    _att_promoted = []
    _conn_att = db_manager.get_connection(case_folder)
    try:
        for _i in range(0, len(suppressed_docs), 900):
            _chunk = suppressed_docs[_i:_i+900]
            _ph = ','.join(['?'] * len(_chunk))
            # Find suppressed emails that have at least one child
            _parents_with_children = {r[0] for r in _conn_att.execute(
                f"SELECT DISTINCT parent_id FROM documents WHERE parent_id IN ({_ph})",
                _chunk
            ).fetchall()}  # db_manager: exempt (read-only analytics query)
            _att_promoted.extend([cn for cn in _chunk if cn in _parents_with_children])
    finally:
        _conn_att.close()

    if _att_promoted:
        _promoted_set = set(_att_promoted)
        suppressed_docs = [cn for cn in suppressed_docs if cn not in _promoted_set]
        inclusive_docs.extend(_att_promoted)
        st.session_state['att_promoted_count'] = len(_att_promoted)
    else:
        st.session_state['att_promoted_count'] = 0
```

**Key points:**
- Uses chunked queries (900-item batches) matching existing pattern in the file
- Read-only query — no writes
- Stores promoted count in session state for UI reporting
- Runs AFTER subject-line fallback so it catches all suppressed emails regardless of how they were classified

#### Change 2: Tag promoted emails with `Inclusive-Attachments` (after tagging Inclusive, ~line 495)

After the `bulk_tag_documents(st.session_state['inclusive_docs'], "Inclusive")` call, add:

```
# Tag attachment-promoted emails so reviewers know why they were retained
if st.session_state.get('att_promoted_count', 0) > 0:
    # att_promoted emails are already in inclusive_docs and got the Inclusive tag above.
    # We need to identify which ones were promoted. Re-derive from the DB:
    # emails tagged Inclusive that have children.
    # OR: simpler — store the promoted list in session state during run_threading.
```

**Better approach:** Store the promoted control numbers in session state during `run_threading()`:

In Change 1, also add:
```
st.session_state['att_promoted_docs'] = _att_promoted if _att_promoted else []
```

Then in the tagging block (after line 495), add:
```
# Tag attachment-promoted emails for reviewer visibility
_att_promo_list = st.session_state.get('att_promoted_docs', [])
if _att_promo_list:
    try:
        bulk_tag_documents(_att_promo_list, "Inclusive-Attachments")
    except Exception as _att_tag_err:
        st.warning(f"⚠️ Attachment-promotion tagging failed: {_att_tag_err}")
```

#### Change 3: Update the metrics display (~lines 427-437)

In the `threading_done` results display, add a line reporting promotions:

After `st.write(f"**Redundant (Skip These):** {sup}")` (line 434), add:
```
_att_promo = st.session_state.get('att_promoted_count', 0)
if _att_promo > 0:
    st.write(f"**↳ Retained for Attachments:** {_att_promo}")
    st.caption("These emails would have been suppressed but were retained because they carry attachments.")
```

#### Change 4: Update audit log entry (~lines 503-506)

In the `ANALYTICS_RUN` audit log details dict, add the promoted count:

```python
details=json.dumps({
    "type": "email_threading",
    "inclusive_count": inc,
    "suppressed_count": sup,
    "attachment_promoted_count": st.session_state.get('att_promoted_count', 0)
})
```

#### Change 5: Clear `Inclusive-Attachments` tag during reset (line 394-396)

In the "Clear & Re-Run Threading" block, add a line to also clear the new tag:

After the existing `REPLACE(tags, 'Inclusive', '')` line, add:
```sql
conn.execute("UPDATE documents SET tags = REPLACE(tags, 'Inclusive-Attachments', '') WHERE source_party = 'Internal' OR source_party IS NULL")
```

**IMPORTANT ORDER:** The `Inclusive-Attachments` replace MUST run BEFORE the `Inclusive` replace, because `Inclusive-Attachments` contains the substring `Inclusive`. If you replace `Inclusive` first, you'd turn `Inclusive-Attachments` into `-Attachments`. So reorder the three existing REPLACE statements to:

1. `REPLACE(tags, 'Inclusive-Attachments', '')`  ← NEW, must be first
2. `REPLACE(tags, 'Thread-Suppressed', '')`  ← existing
3. `REPLACE(tags, 'Inclusive', '')`  ← existing (now safe because Inclusive-Attachments already removed)

#### Change 6: Add `Inclusive-Attachments` to system tag preservation

In `4_Review.py`, the `_SYSTEM_TAGS` set and `_SYS` tuple protect system-computed tags from being cleared during re-imaging. Add `Inclusive-Attachments` to both:

```python
_SYSTEM_TAGS = {'Inclusive', 'Thread-Suppressed', 'NearDupe-Suppressed', 'Inclusive-Attachments'}
```

The `_SYS` tuple already covers it via the `"Inclusive"` prefix check, but add explicitly for clarity if desired.

### File: `db_manager.py`

No changes required. The existing `get_document_children()` function and `bulk_tag_documents()` are sufficient. The suppressed-child propagation block (lines 473-490) will naturally skip the promoted emails because they'll no longer be in `suppressed_docs`.

### File: `5_Production.py`

No changes required. The promoted emails are tagged `Inclusive` like any other inclusive email, so they flow through production sorting normally. Their children (attachments) will NOT receive `Thread-Suppressed` tags (because the parent was removed from the suppressed list before propagation runs), so they remain producible with their parent.

## Data Flow Verification

After this change, the threading sequence is:

1. **Build graph** → classify into `inclusive_docs` and `suppressed_docs`
2. **Subject fallback** → adds more to both lists
3. **NEW: Attachment promotion** → moves attachment-bearing emails from suppressed → inclusive
4. **Store in session state** → both lists are final
5. **User clicks Execute** →
   - Tag suppressed emails as `Thread-Suppressed`
   - **Propagate `Thread-Suppressed` to children of suppressed emails** ← the promoted emails are NOT in this list, so their attachments stay clean
   - Tag inclusive emails as `Inclusive`
   - Tag promoted emails as `Inclusive-Attachments` (informational)

The critical point: because promotion happens BEFORE session state storage and BEFORE tagging, the child-propagation loop at lines 473-490 will never touch the promoted emails' attachments. No further changes to that block needed.

## Testing Checklist

- [ ] Create a thread: Email A (has 2 attachments) → Reply B → Reply C (thread-principal)
- [ ] Run threading. Verify: C is Inclusive, B is Thread-Suppressed, A is Inclusive (promoted)
- [ ] Verify A's attachments do NOT have Thread-Suppressed tag
- [ ] Verify A has both `Inclusive` and `Inclusive-Attachments` tags
- [ ] Verify metrics show "Retained for Attachments: 1"
- [ ] Verify audit log includes `attachment_promoted_count: 1`
- [ ] Clear & Re-Run: verify `Inclusive-Attachments` tag is cleaned up
- [ ] Test with email that has no attachments — should still be suppressed normally
- [ ] Test with single email (no thread) that has attachments — should be Inclusive regardless (no change)

## Defensibility Statement

This feature preserves parent-child document relationships during email thread suppression. When an email carries attachments, it is retained alongside the thread-principal rather than being suppressed, because suppressing the parent would orphan its attachments from production. This is consistent with EDRM best practices for maintaining family integrity in document productions.

## Version Tracking

- `3_Analytics.py`: minor bump (new feature: attachment-aware promotion phase)
- `4_Review.py`: patch bump (system tag list update)
- CHANGELOG entries needed for both
