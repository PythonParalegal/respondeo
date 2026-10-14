# M-4 SQL Migration — Manual Test Plan

**Sprint:** M-4 SQL Migration (Batches 1–7)
**Scope:** 49 new db_manager functions, ~180 call sites migrated
**Tester:** the maintainer
**Date:** ___________

---

## Prerequisites

Before starting, make sure Streamlit, OpenSearch, and any other services are running. You'll need a case with existing data — ingested documents, processed documents, at least one custodian, and ideally a prior production run. If you don't have that, note which sections you had to skip.

**Baseline snapshot:** Before testing, copy your current `case.db` somewhere safe so you can restore if anything goes sideways.

---

## How to Use This Plan

Work through each section in order. Each test has a checkbox, what to do, and what to look for. If something fails, note the symptom in the **Result** column and move on — don't debug during testing. We'll triage failures after.

Mark each test: **PASS** / **FAIL** / **SKIP** (no test data)

---

## SECTION 1 — Dashboard & Page Load (Batch 1: Status Counts)

These are the "does the page even render" tests. Every migrated count query fires on page load, so if numbers appear and don't throw errors, Batch 1 is healthy.

| # | Page | What to Do | What to Look For | Result |
|---|------|-----------|-------------------|--------|
| 1.1 | **Home** | Open the app. Look at the dashboard metrics. | Document counts (ingested, processed, produced, errors) should display as numbers, not errors or blanks. Compare to what you remember — do they look right? | |
| 1.2 | **Home** | Check the review tag breakdown if visible. | Tag counts (Responsive, Privileged, etc.) should render. Zero is fine if nothing's been tagged. | |
| 1.3 | **Processor** | Navigate to the Processor page. | Top metrics row should show document counts, queue stats, and file type breakdown chart. No red error banners. | |
| 1.4 | **Analytics** | Navigate to Analytics → **Dedup Report tab**. | Data reduction stats should load (total docs, exact dupes, near dupes, content dupes). Numbers should be non-negative. | |
| 1.5 | **Sync** | Navigate to Sync → **Filevine tab**. | Sync status metrics should display (Total Valid, Successfully Synced, Pending). | |
| 1.6 | **Sync** | Switch to the **BYOS tab**. | BYOS push/pull metrics should display. | |

**Section 1 verdict:** _______ (all pass / partial / blocked)

---

## SECTION 2 — Search & Bates Lookup (Batch 2: Saved Searches)

These test the search infrastructure in 4_Review.py. You need processed + indexed documents for most of these.

| # | Action | What to Look For | Result |
|---|--------|-------------------|--------|
| 2.1 | Open **Review** page. Run any search (e.g., type a common term and hit enter). | Results appear. No errors. Check the **Recent Searches** sidebar section — your search should appear in the list. | |
| 2.2 | Run 2-3 more searches with different terms. | Recent searches list should grow (up to 10). Newest on top. | |
| 2.3 | Click **💾 Save** on a search. Give it a name. | Search should appear in the **Saved Searches** section of the sidebar. | |
| 2.4 | If the saved search has a globe/global toggle, click it. | Should toggle without error. Refresh the page — toggle state should persist. | |
| 2.5 | Delete a saved search (click the delete icon/button). | Search should disappear from the saved list. No error. | |
| 2.6 | Click **🧹 Clear All** in the Recent Searches section. | All recent searches should clear. | |
| 2.7 | If you have produced documents with Bates numbers: enter a Bates number or range in the Bates lookup field. | Document(s) should resolve. If no productions exist, skip this. | |

**Section 2 verdict:** _______

---

## SECTION 3 — Document Viewer & Tags (Batch 3, Part 1)

This is the highest-traffic part of the migration. Test it carefully.

| # | Action | What to Look For | Result |
|---|--------|-------------------|--------|
| 3.1 | In **Review**, click into a document to open the Document Viewer. | Document metadata should load (filename, custodian, dates, etc.). No error. | |
| 3.2 | Check if parent/family info displays (if the document is an email attachment or has children). | Parent document info should show, or children list should appear if applicable. If standalone document, just confirm no error. | |
| 3.3 | Look at the current tags on the document. | Tags should display (or be empty if untagged). Should not show `None` or error text. | |
| 3.4 | **Change the tags** — add a tag (e.g., "Responsive") and click **Save Tags**. | Success message. Tag should persist if you navigate away and come back to the same document. | |
| 3.5 | **Remove a tag** and save. | Tag should be removed. Verify by navigating away and back. | |
| 3.6 | If you have redaction capability: mark a document as having redactions. | Redaction status should save. Check that it persists on page refresh. | |
| 3.7 | Clear redaction status on the same document. | Status should clear cleanly. | |
| 3.8 | Click **Next** (or "Reviewed — Next") to advance to the next document. | Document should advance. The previous document should now show as reviewed (check `reviewed_by` if visible in the grid). | |

**Section 3 verdict:** _______

---

## SECTION 4 — Review Batches (Batch 3, Part 2)

These test the batch management system in the Review sidebar. **Caution:** "Delete All Batches" is destructive. Only test if you're comfortable recreating them.

| # | Action | What to Look For | Result |
|---|--------|-------------------|--------|
| 4.1 | In **Review** sidebar, open the **📦 Review Batches** expander. | Should show count of unbatched documents. No error on expand. | |
| 4.2 | Set number of batches (e.g., 3) and click **Create N batches**. | Batches should be created. Success message. Batch list should appear below with document counts. | |
| 4.3 | In **Existing Batches**, try assigning a reviewer to a batch (click **Assign**). | Assignment should save. Reviewer name should persist on refresh. | |
| 4.4 | In **Manual Batch Editing**, try moving documents between batches (select source batch, target batch, click **Move**). | Documents should transfer. Both batch counts should update. | |
| 4.5 | Click **🗑️ Delete All Batches** (only if you're OK recreating). | All batches should be removed. Unbatched count should go back up. | |

**Section 4 verdict:** _______

---

## SECTION 5 — Custodian Management (Batch 4)

**High risk:** Rename and Merge are atomic multi-table operations. These are the most important write tests in the plan.

| # | Action | What to Look For | Result |
|---|--------|-------------------|--------|
| 5.1 | Open **Custodians** page. | Inventory bar chart should render with custodian names and document counts. | |
| 5.2 | Select a custodian from the dropdown. | Detail panel should load: Collection Summary metrics (doc count, file types, date range). Profile fields should populate. | |
| 5.3 | Edit a profile field (e.g., title or department) and click **💾 Save Custodian Profile**. | Success message. Refresh the page — field should persist. | |
| 5.4 | **RENAME test:** Pick a custodian, go to the Rename tab. Enter a new name and confirm. | ⚠️ Check THREE things: (a) custodian list updates with new name, (b) documents previously assigned to old name now show new name, (c) chart updates. If any of the three are inconsistent, that's a rollback failure — flag as critical. | |
| 5.5 | **MERGE test:** Pick two custodians. Merge the smaller one into the larger. | ⚠️ Check: (a) source custodian disappears from the list, (b) target custodian's document count increases by the source's count, (c) no orphaned documents. If counts don't add up, flag as critical. | |

**Section 5 verdict:** _______

---

## SECTION 6 — Analytics Reports (Batch 5)

These are read-only queries — lower risk, but important for demo.

| # | Action | What to Look For | Result |
|---|--------|-------------------|--------|
| 6.1 | Open **Analytics → Dedup Report tab**. | Exact dupe clusters, near-dupe clusters, content dupe clusters should all render (tables or charts). Empty results are fine if no dupes exist. Errors are not fine. | |
| 6.2 | Click into a dupe cluster if any exist. | Detail view should expand/load. | |
| 6.3 | Navigate to the **Communication / Custodian Activity** section. Click **🔄 Refresh Communication Data** if prompted. | Custodian activity data should load (chart or table). | |
| 6.4 | Navigate to the **Timeline** section. Click **🔄 Refresh Timeline Data** if prompted. | Timeline chart should render. | |

**Section 6 verdict:** _______

---

## SECTION 7 — Production Management (Batch 6)

**High risk:** These touch Bates number integrity. Only test delete if you have a non-critical production volume you can sacrifice.

| # | Action | What to Look For | Result |
|---|--------|-------------------|--------|
| 7.1 | Open **Production → Validation tab**. Look for the **Bates Gap Analysis** section. | Gap report should render (table showing any gaps in Bates sequence). No error on load. | |
| 7.2 | **DELETE test** (optional — only if you have a test production): Go to Production Cleanup or Management tab. Select a volume and type DELETE to confirm. | Volume should be removed. ⚠️ Check: (a) production records are gone, (b) document cache columns (Bates numbers) are cleared for affected docs, (c) if other productions exist, their Bates numbers are unaffected. | |

**Section 7 verdict:** _______

---

## SECTION 8 — Retry & Settings (Batch 7)

| # | Action | What to Look For | Result |
|---|--------|-------------------|--------|
| 8.1 | On **Processor** page, if there are failed documents, click **🔄 Retry Failed Documents**. | Documents should re-queue. Error count should decrease (or stay same if they fail again for legitimate reasons). No crash. | |
| 8.2 | On **Sync → Filevine tab**, check if the error log displays. | Error details should render as a dataframe. Empty is fine if no sync errors. | |
| 8.3 | If there are sync errors, click **🔄 Retry Failed Syncs**. | Same as 8.1 — should re-queue without crash. | |
| 8.4 | On **Sync → Configuration**, edit a setting (e.g., API URL or project ID) and click **💾 Save Filevine Settings**. | Success message. Refresh — setting should persist. | |
| 8.5 | On **Sync → BYOS tab**, edit BYOS settings and save. | Same — should persist on refresh. | |

**Section 8 verdict:** _______

---

## SECTION 9 — Cross-Cutting Concerns

| # | Check | What to Look For | Result |
|---|-------|-------------------|--------|
| 9.1 | **Audit log:** After completing the write tests above (tag saves, custodian rename, batch creation, etc.), go to the audit log viewer (Home page, admin section). | Your actions should appear in the audit trail with correct timestamps, user, and action descriptions. Missing entries = audit regression. | |
| 9.2 | **Closed case guard:** If you can temporarily close a case, try any write operation (save a tag, rename a custodian, create a batch). | Should be blocked with an appropriate message. If writes succeed on a closed case, flag as critical. | |
| 9.3 | **Role enforcement:** If you can log in as a reviewer (non-manager), try accessing manager-only features. | Should be blocked or hidden. | |

**Section 9 verdict:** _______

---

## Summary

| Section | Scope | Verdict |
|---------|-------|---------|
| 1. Dashboard & Page Load | Batch 1 | |
| 2. Search & Bates | Batch 2 | |
| 3. Document Viewer & Tags | Batch 3 pt 1 | |
| 4. Review Batches | Batch 3 pt 2 | |
| 5. Custodian Management | Batch 4 | |
| 6. Analytics Reports | Batch 5 | |
| 7. Production Management | Batch 6 | |
| 8. Retry & Settings | Batch 7 | |
| 9. Cross-Cutting | All | |

**Overall verdict:** _______

**Blockers found:** _______

**Notes:**


---

## After Testing

Bring your results back to Cowork. I'll triage any failures, determine whether they're migration regressions vs. pre-existing issues, and write fix prompts for CLI Claude if needed. If everything passes, we'll move on to Batch 8 (exempt annotations) and context maintenance.
