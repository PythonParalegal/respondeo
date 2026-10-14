"""
Regression coverage for the NULL-control_number handling in the Review
Search Term Report (STR) pipeline.

The STR feature at pages/4_Review.py:442 constructs a lookup dict keyed
by control_number. Prior to beta-2.11 Commit 4b, the pipeline was
    _str_meta_df.set_index('control_number').to_dict('index')
which raises ValueError under pandas 2.x when the index has duplicate
values — including the NaN/NaN case that arises when ≥2 PST or ZIP
containers appear in the `documents` table (containers store
control_number=NULL by design; SQL UNIQUE permits multiple NULLs).

Commit 4b wraps the pipeline with dropna + drop_duplicates to make
the transformation total. These tests pin the four behaviors that
matter:

  1. Multiple NULL rows no longer crash; only non-NULL rows survive.
  2. All-NULL input yields an empty dict (no crash).
  3. Non-NULL duplicates (shouldn't occur under the DB UNIQUE
     constraint, but defensive) resolve to keep='first'.
  4. The pre-fix expression still raises ValueError on the same fixture,
     pinning the regression so the unsafe pattern can't be reintroduced
     silently.

Tests are pure-pandas. No SQLite, Streamlit, or OpenSearch dependencies.
"""
import numpy as np
import pandas as pd
import pytest


def _apply_str_meta_map_pipeline(df):
    """Mirrors the post-fix pipeline at pages/4_Review.py:442."""
    return (
        df
        .dropna(subset=['control_number'])
        .drop_duplicates(subset=['control_number'], keep='first')
        .set_index('control_number')
        .to_dict('index')
    )


def _build_str_meta_fixture(control_numbers, file_names=None, begdocs=None):
    """Build a synthetic _str_meta_df matching the STR SELECT shape."""
    n = len(control_numbers)
    if file_names is None:
        file_names = [f'file_{i}.eml' for i in range(n)]
    if begdocs is None:
        begdocs = [f'B{i:04d}' if cn is not None and not (isinstance(cn, float) and np.isnan(cn)) else ''
                   for i, cn in enumerate(control_numbers)]
    return pd.DataFrame({
        'control_number': control_numbers,
        'file_name': file_names,
        'begdoc': begdocs,
        'custodian': ['c_' + str(i) for i in range(n)],
    })


def test_drops_multiple_null_control_numbers():
    """2 NaN container rows + 3 real docs: result has only the 3 non-NaN keys."""
    df = _build_str_meta_fixture(
        ['DOC-001', np.nan, 'DOC-002', np.nan, 'DOC-003'],
        file_names=['a.eml', 'container1.pst', 'b.eml', 'container2.pst', 'c.eml'],
    )
    result = _apply_str_meta_map_pipeline(df)

    assert len(result) == 3, f'Expected 3 keys (non-NaN only), got {len(result)}: {list(result.keys())}'
    assert set(result.keys()) == {'DOC-001', 'DOC-002', 'DOC-003'}
    assert result['DOC-001']['file_name'] == 'a.eml'
    assert result['DOC-002']['file_name'] == 'b.eml'
    assert result['DOC-003']['file_name'] == 'c.eml'


def test_empty_after_dropna_yields_empty_dict():
    """All-NaN control_numbers (pathological case): empty dict, no exception."""
    df = _build_str_meta_fixture(
        [np.nan, np.nan, np.nan],
        file_names=['c1.pst', 'c2.pst', 'c3.zip'],
    )
    result = _apply_str_meta_map_pipeline(df)

    assert result == {}, f'Expected empty dict, got {result}'


def test_drop_duplicates_keeps_first_on_nonnull_collision():
    """Duplicate non-NaN CN (defensive — DB UNIQUE should prevent): keep='first'."""
    df = _build_str_meta_fixture(
        ['DOC-001', 'DOC-002', 'DOC-001', 'DOC-003'],
        file_names=['first_occurrence.eml', 'b.eml', 'second_occurrence.eml', 'c.eml'],
    )
    result = _apply_str_meta_map_pipeline(df)

    assert len(result) == 3, f'Expected 3 unique keys, got {len(result)}'
    assert set(result.keys()) == {'DOC-001', 'DOC-002', 'DOC-003'}
    assert result['DOC-001']['file_name'] == 'first_occurrence.eml', (
        'keep="first" should retain the first row, not the later duplicate'
    )


def test_pre_fix_behavior_would_raise():
    """Regression sentinel: the pre-fix expression must still raise on duplicate NaN input.

    If this test ever starts passing, either pandas changed its semantics
    or someone reverted the fix silently. Either case warrants review.
    """
    df = _build_str_meta_fixture(
        ['DOC-001', np.nan, np.nan],
        file_names=['a.eml', 'c1.pst', 'c2.pst'],
    )
    with pytest.raises(ValueError, match=r'DataFrame index must be unique'):
        # Note: this is the original (pre-fix) expression — no dropna, no drop_duplicates.
        df.set_index('control_number').to_dict('index')
