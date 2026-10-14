"""
Regression tests pinning the canonical OS-id contract for the two
shape-adapter helpers in os_manager:

    - cn_from_hit(hit)       — OS hit dict  -> raw control_number
    - compute_os_id(...)     — doc identifiers -> OS _id string

These are the symmetric pair that resolve Flag #28 (Review text-search /
reindex dropping inbound hits due to the `_id`-vs-`control_number`
ambiguity between internal docs (`_id == control_number`) and inbound docs
(`_id == f"{production_volume}-{control_number}"`).

test_inbound_shape and test_round_trip_inbound are the load-bearing
Flag #28 regression pins: they would fail against the pre-fix inline
pattern that consumed `hit["_id"]` directly.
"""
import pytest

from os_manager import cn_from_hit, compute_os_id


def _make_hit(_id, source_cn=None, extra_source=None):
    """Build a fake OS hit dict.

    With no _source content at all, omit the `_source` key entirely so we
    can exercise the projection-stripped search-hit path.
    """
    source = {}
    if source_cn is not None:
        source["control_number"] = source_cn
    if extra_source:
        source.update(extra_source)
    return {"_id": _id, "_source": source} if source else {"_id": _id}


class TestCnFromHit:
    def test_internal_shape(self):
        hit = _make_hit("DOC-001", source_cn="DOC-001")
        assert cn_from_hit(hit) == "DOC-001"

    def test_inbound_shape(self):
        """The Flag #28 regression-pin: composite _id, raw cn in _source."""
        hit = _make_hit("VOL1-DOC-001", source_cn="DOC-001")
        assert cn_from_hit(hit) == "DOC-001"

    def test_no_source(self):
        """Search hit with projection-stripped _source: fall through to _id."""
        hit = {"_id": "DOC-001"}
        assert cn_from_hit(hit) == "DOC-001"

    def test_source_without_control_number(self):
        """_source present but lacks control_number: fall through to _id."""
        hit = _make_hit("DOC-001", extra_source={"other": "value"})
        assert cn_from_hit(hit) == "DOC-001"

    def test_raises_on_no_id_and_no_cn(self):
        """Catastrophic OS shape (neither _id nor _source.control_number)."""
        with pytest.raises(KeyError):
            cn_from_hit({"_source": {}})


class TestComputeOsId:
    def test_internal_returns_cn(self):
        assert compute_os_id("Internal", None, "DOC-001") == "DOC-001"
        assert compute_os_id("Internal", "ignored", "DOC-001") == "DOC-001"

    def test_inbound_returns_composite(self):
        assert compute_os_id("Opposing", "VOL1", "DOC-001") == "VOL1-DOC-001"

    def test_inbound_raises_on_missing_volume(self):
        with pytest.raises(ValueError, match="production_volume"):
            compute_os_id("Opposing", None, "DOC-001")
        with pytest.raises(ValueError, match="production_volume"):
            compute_os_id("Opposing", "", "DOC-001")


class TestRoundTrip:
    def test_round_trip_inbound(self):
        """Pin the symmetric-pair contract: compute_os_id <-> cn_from_hit."""
        os_id = compute_os_id("Opposing", "VOL1", "DOC-001")
        hit = _make_hit(os_id, source_cn="DOC-001")
        assert cn_from_hit(hit) == "DOC-001"
