# Claude Code Prompt: Fix Redaction Canvas Page Navigation Bug

## Bug

`StreamlitAPIException: st.session_state.redact_jump_DOC-000007 cannot be modified after the widget with key redact_jump_DOC-000007 is instantiated.`

Traceback points to `4_Review.py` line 3775:
```python
st.session_state[_r_jump_key] = str(_r_page_idx + 2)
```

## Root Cause

The ◀/▶ buttons write to `_r_jump_key` (the text_input's widget key) AFTER the text_input has already rendered and claimed that key. Streamlit prohibits writing to a widget-owned session state key after the widget is instantiated.

- Line 3756: ◀ button writes to `_r_jump_key` — works sometimes because it renders before text_input, but is still fragile
- Line 3775: ▶ button writes to `_r_jump_key` — always fails because text_input (line 3758) has already been instantiated

## Fix: Deferred Pending Navigation Pattern

This pattern already exists in the codebase for `_load_saved_query` / `_pending_search_restore`. Apply the same approach:

### Step 1: Add pending nav check BEFORE any navigation widgets render

Find this block (around line 3748-3752):
```python
                                # Navigation
                                _r_jump_key = f"redact_jump_{current_cn}"
                                # Seed the text input key on first render only
                                if _r_jump_key not in st.session_state:
                                    st.session_state[_r_jump_key] = str(_r_page_idx + 1)
```

Replace with:
```python
                                # Navigation — deferred pending pattern
                                _r_jump_key = f"redact_jump_{current_cn}"
                                _r_nav_pending_key = f"_redact_nav_pending_{current_cn}"

                                # Apply any pending navigation from last rerun's button click
                                # (must happen BEFORE text_input claims the key)
                                _r_nav_pending = st.session_state.pop(_r_nav_pending_key, None)
                                if _r_nav_pending is not None:
                                    st.session_state[_r_page_key] = _r_nav_pending
                                    _r_page_idx = _r_nav_pending  # Update local var too
                                    st.session_state[_r_jump_key] = str(_r_nav_pending + 1)
                                elif _r_jump_key not in st.session_state:
                                    # Seed the text input key on first render only
                                    st.session_state[_r_jump_key] = str(_r_page_idx + 1)
```

### Step 2: Change ◀ button to use pending pattern

Find (line 3754-3757):
```python
                                if _r_nc1.button("◀", key=f"redact_prev_{current_cn}", disabled=(_r_page_idx == 0), width='stretch'):
                                    st.session_state[_r_page_key] = _r_page_idx - 1
                                    st.session_state[_r_jump_key] = str(_r_page_idx)
                                    st.rerun()
```

Replace with:
```python
                                if _r_nc1.button("◀", key=f"redact_prev_{current_cn}", disabled=(_r_page_idx == 0), width='stretch'):
                                    st.session_state[_r_nav_pending_key] = _r_page_idx - 1
                                    st.rerun()
```

### Step 3: Change ▶ button to use pending pattern

Find (line 3773-3776):
```python
                                if _r_nc4.button("▶", key=f"redact_next_{current_cn}", disabled=(_r_page_idx == _r_total_pages - 1), width='stretch'):
                                    st.session_state[_r_page_key] = _r_page_idx + 1
                                    st.session_state[_r_jump_key] = str(_r_page_idx + 2)
                                    st.rerun()
```

Replace with:
```python
                                if _r_nc4.button("▶", key=f"redact_next_{current_cn}", disabled=(_r_page_idx == _r_total_pages - 1), width='stretch'):
                                    st.session_state[_r_nav_pending_key] = _r_page_idx + 1
                                    st.rerun()
```

## How the Fix Works

1. Button click → sets a **pending key** (not the widget key) → triggers `st.rerun()`
2. On the next render pass, BEFORE the text_input widget is created, the pending value is popped and applied to both `_r_page_key` (actual page index) and `_r_jump_key` (text_input display value)
3. Text_input then renders with the correct value already in session state
4. No write to a widget-owned key after instantiation → no error

## What NOT To Do

- Do NOT remove the text_input widget or replace it with st.write — the jump-to-page feature is useful
- Do NOT change the overall layout or column structure
- Do NOT touch the canvas, marks, save/clear logic — only the nav block
- This is a BUGFIX only — no feature additions, no CHANGELOG (the M-4 sprint will capture it)

## Testing

After the fix, verify:
1. ◀ and ▶ buttons navigate pages without errors
2. Typing a page number into the text input and pressing Enter jumps to that page
3. Page state persists when switching between documents and switching back
4. Marks on each page still display correctly after navigation
