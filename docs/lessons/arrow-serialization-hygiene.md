# Arrow Serialization Hygiene

**One-sentence summary:** Use `None` (not `''`) for missing numeric values in DataFrames — Streamlit serializes DataFrames through Arrow, and Arrow rejects mixed string/numeric columns with a cryptic error.

## The pattern

Streamlit's `st.dataframe()` passes DataFrames to the browser via Apache Arrow. Arrow is strict about column types: every value in a column must be compatible with the column's inferred dtype. pandas, by contrast, is permissive — a column can contain mixed types and pandas will silently widen the dtype to `object` (Python's catch-all) to accommodate them. The collision between "pandas accepts this" and "Arrow rejects this" produces a failure that looks like a Streamlit display bug but is actually a data-hygiene bug upstream.

The specific failure: a column intended to hold numeric values (`int`, `float`) that contains even one empty-string `''` entry gets its dtype widened to `object`. pandas operations continue to work because Python handles mixed types at runtime. Streamlit's `st.dataframe()` then tries to serialize the column through Arrow; Arrow sees an `object` column mixing strings and floats; Arrow raises `pyarrow.lib.ArrowInvalid` with a cryptic message about failing to unify types. The user sees "display crashed" and cannot tell from the error where the bad data originated.

The fix: use `None` for missing numeric values. `None` becomes `NaN` in numeric columns (or `pd.NA` if the column is `Int64` nullable), which Arrow handles correctly. `''` does not — it stays a string and poisons the column's dtype inference. The rule applies to any DataFrame destined for a Streamlit display surface: before returning, verify column dtypes match expectations, and replace any `''` in numeric columns with `None`.

## Concrete example

**Sprint:** beta-2.9 privilege log fixes (`docs/archive/specs/Privilege_Log_Fixes_Round2.md` Bug 3).

The privilege log DataFrame's `page_count` and `redaction_pages` columns were built from per-row dict construction. Some rows had valid integer counts; others had empty string `''` when the source document had no page count recorded. The resulting DataFrame column's dtype was `object`, not `int` or `float`. Streamlit's `st.dataframe()` call on the privilege log preview panel crashed with an Arrow error.

The fix:

```python
# Before (breaks):
'page_count':      int(r['page_count']) if pd.notna(r['page_count']) else '',
'redaction_pages': int(r['redacted_page_count']) if pd.notna(r['redacted_page_count']) and r['redacted_page_count'] > 0 else '',

# After (works):
'page_count':      int(r['page_count']) if pd.notna(r['page_count']) else None,
'redaction_pages': int(r['redacted_page_count']) if pd.notna(r['redacted_page_count']) and r['redacted_page_count'] > 0 else None,
```

With `None` as the fallback, missing values become `NaN` in a float column (pandas' default for integer columns that contain NaN). Arrow serializes float-with-NaN cleanly. The display works.

## How to apply

- When constructing a DataFrame destined for Streamlit display, use `None` (or `pd.NA`) for missing numeric values. Never `''`.
- For string columns, `''` is fine — strings are already the column's dtype.
- Before returning a DataFrame from a `db_manager` function or building one in a page, check each column's intended dtype:
  ```python
  print(df.dtypes)
  ```
  Any column you expected to be numeric that shows `object` is a suspect — grep the construction logic for `''` fallbacks.
- `pd.to_numeric(df['col'], errors='coerce')` forces a column to numeric and converts non-numeric entries (including `''`) to `NaN`. A cheap hedge when you're not sure about your upstream data.
- Tests that exercise display paths should assert DataFrame dtypes match expectations before the simulated display. A test that only checks displayed output will miss this class of bug because the display itself is what crashes.

## See also

- **Related lessons:** `docs/lessons/no-silent-default.md`
- **Source:** `docs/archive/specs/Privilege_Log_Fixes_Round2.md` Bug 3 (Page Count / Redacted Pages Arrow fix)
- **Relevant code:** `pages/5_Production.py` privilege log DataFrame construction; any `db_manager.py` function returning a DataFrame
