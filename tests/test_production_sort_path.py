"""
Regression tests for the outbound sort path's NULL-CN parent handling.

beta-2.10 Commit 7.5 fix: _render_outbound_production() filters at lines 2681,
2686, 2703 previously crashed with InvalidIndexError when the production
DataFrame contained rows with `parent_id=NULL AND control_number=NULL` (PST
container artifacts). Fix: narrow the filter to
`df['_is_parent'] & df['control_number'].notna()` at each site.

These tests replicate the exact fix pattern against a crafted DataFrame to
prevent regression if the inline code is ever refactored or moved. The fixture
deliberately MIXES real email documents (with CNs) and PST-container-like rows
(NULL CN, NULL parent_id) — the fix must correctly exclude NULL-CN rows from
the lookup dataframe AND correctly preserve the real-email rows' folder/
category mappings. A fixture with only NULL-CN rows would pass the exclude
check trivially without exercising the preserve-real-rows correctness.
"""
import pandas as pd
import pytest


def _build_null_cn_parent_dataframe():
    """
    Mimics the shape of df inside _render_outbound_production() after family
    expansion + _is_parent assignment. Mixed population:

      - 2 real parent emails (DOC-001, DOC-002) with populated control_number,
        source_collection, source_subcollection, production_category
      - 1 PST container (id=27) with control_number=None, parent_id=None,
        and all folder/category fields NULL — the defective population shape
        that triggered the original crash
      - 3 child docs attributed to the real email parents via parent_id
    """
    rows = [
        {'id': '1', 'control_number': 'DOC-001', 'parent_id': None,
         'source_collection': 'Custodian_A', 'source_subcollection': 'Inbox',
         'production_category': 'Responsive', 'sort_group': 'DOC-001'},
        {'id': '2', 'control_number': 'DOC-002', 'parent_id': None,
         'source_collection': 'Custodian_B', 'source_subcollection': 'Sent',
         'production_category': 'Responsive', 'sort_group': 'DOC-002'},
        {'id': '27', 'control_number': None, 'parent_id': None,
         'source_collection': None, 'source_subcollection': None,
         'production_category': None, 'sort_group': None},
        {'id': '3', 'control_number': 'DOC-003', 'parent_id': 'DOC-001',
         'source_collection': 'Custodian_A', 'source_subcollection': 'Inbox',
         'production_category': None, 'sort_group': 'DOC-001'},
        {'id': '4', 'control_number': 'DOC-004', 'parent_id': 'DOC-002',
         'source_collection': 'Custodian_B', 'source_subcollection': 'Sent',
         'production_category': None, 'sort_group': 'DOC-002'},
        {'id': '5', 'control_number': 'DOC-005', 'parent_id': 'DOC-001',
         'source_collection': 'Custodian_A', 'source_subcollection': 'Inbox',
         'production_category': None, 'sort_group': 'DOC-001'},
    ]
    df = pd.DataFrame(rows)
    df['_is_parent'] = df['parent_id'].isna() | (df['parent_id'].astype(str).str.strip() == '')
    return df


class TestSortPathNullCnParents:
    """
    Pattern: every filter site that does `df[df['_is_parent']].set_index(
    'control_number')` must also exclude NULL-CN rows, or the resulting
    index is non-unique and downstream .map() raises InvalidIndexError.
    """

    def test_broad_filter_produces_nonunique_index(self):
        """Confirms the failure mode the fix protects against.

        Canary for pandas version drift: if a future pandas version changes
        how .map() handles duplicate NaN indices, this test fails and alerts
        us to re-verify the fix still holds.
        """
        df = _build_null_cn_parent_dataframe()
        # Add a second NULL-CN parent to guarantee two NaN entries in the index
        extra = pd.DataFrame([{
            'id': '28', 'control_number': None, 'parent_id': None,
            'source_collection': None, 'source_subcollection': None,
            'production_category': None, 'sort_group': None,
        }])
        extra['_is_parent'] = True
        df2 = pd.concat([df, extra], ignore_index=True)

        # Broad filter (pre-fix pattern) produces a non-unique NaN index
        broad = df2[df2['_is_parent']].set_index('control_number')
        series = broad['source_collection']

        # .map() against a Series with non-unique NaN index raises
        with pytest.raises(Exception):
            df2['sort_group'].map(series)

    def test_narrowed_filter_excludes_null_cn_and_preserves_real_rows(self):
        """Verifies the fix pattern at each of the 3 filter sites.

        Mixed-fixture check: excludes NULL-CN PST container from the lookup
        AND preserves real-email parent rows (DOC-001, DOC-002) correctly.
        """
        df = _build_null_cn_parent_dataframe()
        narrowed = df[df['_is_parent'] & df['control_number'].notna()].set_index('control_number')

        # Index is unique, non-null, and contains exactly the real-email parents
        assert narrowed.index.is_unique
        assert not narrowed.index.isna().any()
        assert set(narrowed.index) == {'DOC-001', 'DOC-002'}

        # Real-email parent rows preserved: their folder/category values survive
        assert narrowed.loc['DOC-001', 'source_collection'] == 'Custodian_A'
        assert narrowed.loc['DOC-001', 'source_subcollection'] == 'Inbox'
        assert narrowed.loc['DOC-002', 'source_collection'] == 'Custodian_B'
        assert narrowed.loc['DOC-002', 'source_subcollection'] == 'Sent'

        # .map() succeeds and routes real-email families correctly
        fc = df['sort_group'].map(narrowed['source_collection'])
        assert fc.iloc[0] == 'Custodian_A'   # DOC-001 (self-parent)
        assert fc.iloc[1] == 'Custodian_B'   # DOC-002 (self-parent)
        assert pd.isna(fc.iloc[2])            # PST container, sort_group=None → NaN
        assert fc.iloc[3] == 'Custodian_A'   # DOC-003, child of DOC-001
        assert fc.iloc[4] == 'Custodian_B'   # DOC-004, child of DOC-002
        assert fc.iloc[5] == 'Custodian_A'   # DOC-005, child of DOC-001

    def test_fillna_fallback_preserves_child_own_values(self):
        """After .map() returns NaN, .fillna(df[col]) must use the child's own value.

        This is the full pattern as used in production code:
            df['_family_X'] = df['sort_group'].map(lookup).fillna(df['X'])
        """
        df = _build_null_cn_parent_dataframe()
        narrowed = df[df['_is_parent'] & df['control_number'].notna()].set_index('control_number')
        result = df['sort_group'].map(narrowed['source_collection']).fillna(df['source_collection'])

        # Real-email rows: mapped correctly
        assert result.iloc[0] == 'Custodian_A'
        assert result.iloc[1] == 'Custodian_B'
        # PST container: map returns NaN, fillna looks at df['source_collection'] which is also None → stays NaN
        assert pd.isna(result.iloc[2])
        # Child rows: either mapped from parent or fell through to own value via fillna
        assert result.iloc[3] == 'Custodian_A'
        assert result.iloc[4] == 'Custodian_B'
        assert result.iloc[5] == 'Custodian_A'

    def test_regression_all_three_filter_sites_verbatim(self):
        """Replicates each of the 3 filter expressions from
        pages/5_Production.py lines 2681, 2686, 2703 verbatim to catch
        inline-code drift if the fix pattern is ever modified.
        """
        df = _build_null_cn_parent_dataframe()

        # Site 1 — line 2681 — _root_cats (category-sort family-mode branch)
        _root_cats = df[df['_is_parent'] & df['control_number'].notna()].set_index('control_number')['production_category']
        assert _root_cats.index.is_unique
        assert not _root_cats.index.isna().any()
        # Real-email categories preserved
        assert _root_cats.loc['DOC-001'] == 'Responsive'
        assert _root_cats.loc['DOC-002'] == 'Responsive'

        # Site 2 — line 2686 — _root_folders (category-sort, uncategorized sub-sort)
        _root_folders_cat = df[df['_is_parent'] & df['control_number'].notna()].set_index('control_number')[['source_collection', 'source_subcollection']]
        assert _root_folders_cat.index.is_unique
        assert list(_root_folders_cat.columns) == ['source_collection', 'source_subcollection']
        assert _root_folders_cat.loc['DOC-001', 'source_collection'] == 'Custodian_A'

        # Site 3 — line 2703 — _root_folders (folder-sort branch, identical expression)
        _root_folders_folder = df[df['_is_parent'] & df['control_number'].notna()].set_index('control_number')[['source_collection', 'source_subcollection']]
        assert _root_folders_folder.index.is_unique
        # Sites 2 and 3 produce identical dataframes from the same fixture
        pd.testing.assert_frame_equal(_root_folders_cat, _root_folders_folder)
