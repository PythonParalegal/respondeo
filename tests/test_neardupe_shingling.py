"""
Regression tests for the NearDupe shingling algorithm (Flag #22, beta-2.16 S-1a).

Pins the contract of `pages/3_Analytics.py:_compute_minhash_signature()`:
  - k-gram (5-word sliding window) shingling, NOT word-level (k=1) shingling
  - template-distinct documents (same-vendor invoices) do NOT cluster at the
    unchanged production threshold (0.90) — k=5 alone delivers the Flag #22 fix
  - true FW-style near-dupes (thin forwarding preamble + shared body) DO cluster
  - RE replies with substantive new content are DISTINCT by design (NOT clustered)
  - completely-unrelated docs do NOT cluster; the threshold parameter gates

Fixture-design note (per the S-1a v4/v5 calibration arc): true-near-dupe
fixtures use NARROW preambles ("FW: " / "FW: FW: ") on a ~170-token body so the
exact Jaccard is ~0.99. That keeps the MinHash estimate (num_perm=128, variance
~0.088) well above the 0.90 threshold even under variance, so every in-cluster
pair is a direct LSH candidate and MinHashLSH.query() returns the full cluster
without needing transitive closure. (A wider-preamble fixture lands at ~0.91
exact / ~0.89 estimate and fails to cluster — see check report v4.)

Streamlit pages aren't import-safe (top-level access gate, st.tabs, OS client
at module load). AST surgery extracts just the target function definition
without executing the rest of the page (pattern: tests/test_review_inbound_badge.py),
injecting MinHash into the exec namespace since the function body calls it.
"""
import ast
import pathlib
import pytest
from datasketch import MinHash, MinHashLSH


def _load_compute_minhash_signature():
    page_path = pathlib.Path(__file__).parent.parent / "pages" / "3_Analytics.py"
    source = page_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_compute_minhash_signature":
            mod = ast.Module(body=[node], type_ignores=[])
            ns = {"MinHash": MinHash}  # inject — function body calls MinHash(...)
            exec(compile(mod, str(page_path), "exec"), ns)
            return ns["_compute_minhash_signature"]
    raise RuntimeError("_compute_minhash_signature not found in pages/3_Analytics.py")


_compute_minhash_signature = _load_compute_minhash_signature()


class TestShinglingBasics:
    def test_empty_content_returns_empty_signature(self):
        m = _compute_minhash_signature("")
        assert len(m) == 128  # MinHash always has num_perm hash values

    def test_content_shorter_than_k_returns_empty_signature(self):
        m = _compute_minhash_signature("only four words here")  # 4 tokens < k=5
        assert m is not None  # caller's len(tokens) < 5 guard skips these before LSH

    def test_raises_on_invalid_k(self):
        with pytest.raises(ValueError, match="k must be >= 1"):
            _compute_minhash_signature("some content here for testing", k=0)

    def test_k_equals_token_count_produces_one_shingle(self):
        """A doc with exactly k tokens produces exactly one shingle (the whole
        token sequence). Verified by Jaccard==1.0 against a hand-built MinHash."""
        m = _compute_minhash_signature("alpha beta gamma delta epsilon")  # 5 tokens
        expected = MinHash(num_perm=128)
        expected.update("alpha beta gamma delta epsilon".encode("utf8"))
        assert m.jaccard(expected) == 1.0


class TestFalsePositiveSuppression:
    """The Flag #22 regression-pin: template-distinct docs must NOT cluster."""

    def test_template_distinct_invoices_do_not_cluster(self):
        """Three realistic-length invoices from one vendor template with distinct
        numbers, dates, and amounts must NOT cluster at the unchanged 0.90
        threshold (measured exact Jaccard ~0.80 under k=5 — well below 0.90)."""
        invoice_template = (
            "Acme Vendor Corporation 100 Industry Way Suite 200 Springfield "
            "Illinois 62701 Phone 555 123 4567 Email billing acmevendor com "
            "INVOICE "
            "Bill To: Client Industries LLC Attention Accounts Payable "
            "200 Commerce Street Floor 3 Chicago Illinois 60601 "
            "Payment Terms: Net 30 days from invoice date Late payment subject "
            "to monthly finance charge of 1.5 percent Remit payment to address "
            "above or via electronic transfer to account on file "
            "Description Quantity Unit Price Amount "
            "Consulting services per engagement letter "
            "Project management hours included in retainer "
            "Travel expenses reimbursable per policy "
            "Materials and supplies subject to invoice review "
            "Subtotal subject to applicable taxes "
            "Thank you for your business Questions contact accounts receivable "
        )
        invoices = [
            invoice_template + "Invoice Number 1001 Date January 15 2026 "
                               "Total Amount Due 1234 dollars and 56 cents",
            invoice_template + "Invoice Number 1002 Date February 20 2026 "
                               "Total Amount Due 5678 dollars and 90 cents",
            invoice_template + "Invoice Number 1003 Date March 25 2026 "
                               "Total Amount Due 9012 dollars and 34 cents",
        ]
        lsh = MinHashLSH(threshold=0.90, num_perm=128)
        sigs = []
        for i, content in enumerate(invoices):
            m = _compute_minhash_signature(content)
            lsh.insert(f"inv-{i}", m)
            sigs.append(m)
        for i, m in enumerate(sigs):
            result = lsh.query(m)
            assert result == [f"inv-{i}"], (
                f"Invoice inv-{i} clustered with {result} — false positive."
            )


class TestTrueNearDupeClustering:
    """True FW-style near-dupes (thin preamble + shared body) MUST cluster.
    RE replies with substantive new content are distinct by design (NOT clustered)."""

    def test_fw_email_near_dupes_do_cluster(self):
        """~170-token body with NARROW (2-4 token) forwarding preambles. Narrow
        preambles give exact Jaccard ~0.99, keeping MinHash estimates well above
        0.90 even under variance, so all three cluster (measured)."""
        body = (
            "Hi team please find attached the revised draft of the master "
            "services agreement that we discussed in yesterday's meeting "
            "with outside counsel I have incorporated all of the changes "
            "requested by the legal department including the new "
            "indemnification language in section 8 the updated limitation "
            "of liability cap in section 12 and the modified dispute "
            "resolution provisions in section 18 please review carefully "
            "and provide your feedback by end of week so that we can "
            "circulate to opposing counsel before the deadline next "
            "Tuesday I am particularly interested in your perspective on "
            "the carve-outs we added to the indemnification clause and "
            "whether the new liability cap is acceptable given the "
            "expected scope of the engagement also please note that I "
            "have updated the payment terms to reflect the milestones "
            "we agreed to during the negotiation last month let me know "
            "if you have any questions or concerns and we can schedule "
            "a call to discuss best regards John Smith Senior Counsel "
            "Legal Department Phone 555 234 5678 Email jsmith company com"
        )
        emails = [
            body,                  # Original
            "FW: " + body,         # 2-token preamble → exact Jaccard ~0.99
            "FW: FW: " + body,     # 4-token preamble → exact Jaccard ~0.98
        ]
        lsh = MinHashLSH(threshold=0.90, num_perm=128)
        sigs = []
        for i, content in enumerate(emails):
            m = _compute_minhash_signature(content)
            lsh.insert(f"email-{i}", m)
            sigs.append(m)
        cluster_for_original = sorted(lsh.query(sigs[0]))
        assert cluster_for_original == ["email-0", "email-1", "email-2"], (
            f"FW emails failed to cluster: only {cluster_for_original} together."
        )

    def test_re_with_substantive_reply_NOT_clustered(self):
        """RE: replies that add substantive new reply content are DISTINCT
        documents by design — they contain new responsive material. Should NOT
        cluster with the original (measured exact Jaccard ~0.49)."""
        body = (
            "Hi team please find attached the revised draft of the master "
            "services agreement that we discussed in yesterday's meeting "
            "with outside counsel I have incorporated all of the changes "
            "requested by the legal department including the new "
            "indemnification language in section 8 the updated limitation "
            "of liability cap in section 12 and the modified dispute "
            "resolution provisions in section 18 please review carefully "
            "and provide your feedback by end of week best regards John"
        )
        reply = (
            "John I reviewed the draft and have several substantive concerns "
            "about the indemnification language specifically the carve-out "
            "for gross negligence appears to be too narrow given the nature "
            "of the work we should also reconsider the liability cap which "
            "seems low for an engagement of this scope let us schedule a "
            "call this week to discuss before circulating Sarah"
        )
        original = body
        re_with_reply = (
            "From Sarah Jones Sent Tuesday RE Master Services Agreement "
            f"{reply} On Monday John Smith wrote {body}"
        )
        lsh = MinHashLSH(threshold=0.90, num_perm=128)
        m_orig = _compute_minhash_signature(original)
        m_re = _compute_minhash_signature(re_with_reply)
        lsh.insert("orig", m_orig)
        lsh.insert("re", m_re)
        assert lsh.query(m_orig) == ["orig"], (
            "RE-with-reply incorrectly clustered with original — should be distinct."
        )
        assert lsh.query(m_re) == ["re"]


class TestUnrelatedDocsControl:
    """Control: completely-different docs must NOT cluster; threshold gates."""

    def test_unrelated_docs_do_not_cluster(self):
        docs = [
            "The quick brown fox jumps over the lazy dog repeatedly every "
            "morning by the riverbank where the willows grow tall and the "
            "currents flow swiftly past the old wooden bridge",
            "Database migration scripts should be tested in staging "
            "environments before deployment to production systems with full "
            "rollback procedures documented and reviewed by the operations team",
            "Mary had a little lamb whose fleece was white as snow and "
            "everywhere that Mary went the lamb was sure to follow even "
            "to school one day which was against the rules",
        ]
        lsh = MinHashLSH(threshold=0.90, num_perm=128)
        sigs = []
        for i, content in enumerate(docs):
            m = _compute_minhash_signature(content)
            lsh.insert(f"doc-{i}", m)
            sigs.append(m)
        for i, m in enumerate(sigs):
            assert lsh.query(m) == [f"doc-{i}"]

    def test_threshold_boundary_just_below_cutoff(self):
        """A pair ~0.81 similar (shared 30-token base, distinct 3-token tails)
        is a singleton at the production 0.90 threshold but clusters at a
        permissive 0.60 — confirms the threshold parameter actually gates.
        (Measured exact Jaccard 0.812 / est 0.773.)"""
        base = " ".join(f"w{i}" for i in range(30))
        doc_a = base + " alpha beta gamma"
        doc_b = base + " omega psi chi"
        ma = _compute_minhash_signature(doc_a)
        mb = _compute_minhash_signature(doc_b)

        strict = MinHashLSH(threshold=0.90, num_perm=128)
        strict.insert("a", ma)
        strict.insert("b", mb)
        assert strict.query(ma) == ["a"], "Sub-0.90 pair must not cluster at 0.90."

        loose = MinHashLSH(threshold=0.60, num_perm=128)
        loose.insert("a", ma)
        loose.insert("b", mb)
        assert set(loose.query(ma)) == {"a", "b"}, "Pair should cluster at 0.60."
