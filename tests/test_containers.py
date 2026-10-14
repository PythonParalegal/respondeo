"""
test_containers.py — regression tests for container_exploder.py

Tests ZIP and EML extraction paths only. Outlook COM and libpff paths
are excluded from the headless suite (require installed software).
MSG extraction is also COM-dependent and excluded.
"""
import os
import pytest
import container_exploder


# ---------------------------------------------------------------------------
# ZIP extraction
# ---------------------------------------------------------------------------

class TestZipExtraction:

    def test_two_files_extracted(self, tmp_path, sample_zip):
        out = str(tmp_path / "out")
        os.makedirs(out)
        results = container_exploder.explode_container(sample_zip, out)
        assert len(results) == 2

    def test_result_tuples_have_three_elements(self, tmp_path, sample_zip):
        out = str(tmp_path / "out")
        os.makedirs(out)
        results = container_exploder.explode_container(sample_zip, out)
        for item in results:
            assert len(item) == 3, "Each result must be (filename, physical_path, logical_path)"

    def test_extracted_files_exist_on_disk(self, tmp_path, sample_zip):
        out = str(tmp_path / "out")
        os.makedirs(out)
        results = container_exploder.explode_container(sample_zip, out)
        for _, physical_path, _ in results:
            assert os.path.isfile(physical_path), f"Expected file at {physical_path}"

    def test_extracted_content_matches_original(self, tmp_path, sample_zip):
        out = str(tmp_path / "out")
        os.makedirs(out)
        results = container_exploder.explode_container(sample_zip, out)
        # Find the first-level file (doc_a.txt)
        doc_a = next(
            (r for r in results if r[0] == "doc_a.txt"),
            None,
        )
        assert doc_a is not None
        with open(doc_a[1], "r") as f:
            assert f.read() == "Content of document A."

    def test_logical_path_includes_zip_name(self, tmp_path, sample_zip):
        out = str(tmp_path / "out")
        os.makedirs(out)
        results = container_exploder.explode_container(sample_zip, out)
        zip_name = os.path.basename(sample_zip)
        for _, _, logical_path in results:
            assert logical_path.startswith(zip_name), (
                f"Logical path '{logical_path}' should start with zip name '{zip_name}'"
            )

    def test_uuid_prefix_prevents_name_collisions(self, tmp_path, sample_zip):
        out = str(tmp_path / "out")
        os.makedirs(out)
        results = container_exploder.explode_container(sample_zip, out)
        physical_names = [os.path.basename(r[1]) for r in results]
        # All physical names must be unique (UUID prefix ensures this)
        assert len(physical_names) == len(set(physical_names))

    def test_non_container_returns_empty(self, tmp_path):
        txt_file = str(tmp_path / "plain.txt")
        with open(txt_file, "w") as f:
            f.write("just text")
        results = container_exploder.explode_container(txt_file, str(tmp_path))
        assert results == []


# ---------------------------------------------------------------------------
# EML extraction
# ---------------------------------------------------------------------------

class TestEmlExtraction:

    def test_attachment_extracted_from_sample_eml(self, tmp_path, sample_eml):
        out = str(tmp_path / "out")
        os.makedirs(out)
        results = container_exploder.explode_container(sample_eml, out)
        assert len(results) == 1

    def test_extracted_attachment_filename(self, tmp_path, sample_eml):
        out = str(tmp_path / "out")
        os.makedirs(out)
        results = container_exploder.explode_container(sample_eml, out)
        filename, _, _ = results[0]
        assert filename == "exhibit_a.txt"

    def test_extracted_attachment_exists_on_disk(self, tmp_path, sample_eml):
        out = str(tmp_path / "out")
        os.makedirs(out)
        results = container_exploder.explode_container(sample_eml, out)
        _, physical_path, _ = results[0]
        assert os.path.isfile(physical_path)

    def test_extracted_attachment_content(self, tmp_path, sample_eml):
        out = str(tmp_path / "out")
        os.makedirs(out)
        results = container_exploder.explode_container(sample_eml, out)
        _, physical_path, _ = results[0]
        with open(physical_path, "rb") as f:
            content = f.read()
        # Base64 "SGVsbG8gZnJvbSBleGhpYml0IEE=" decodes to "Hello from exhibit A"
        assert content == b"Hello from exhibit A"

    def test_eml_without_attachments_returns_empty(self, tmp_path):
        eml_path = str(tmp_path / "no_attach.eml")
        with open(eml_path, "w") as f:
            f.write(
                "From: a@example.com\r\n"
                "To: b@example.com\r\n"
                "Subject: Plain\r\n"
                "Content-Type: text/plain\r\n\r\n"
                "No attachments here.\r\n"
            )
        out = str(tmp_path / "out")
        os.makedirs(out)
        results = container_exploder.explode_container(eml_path, out)
        assert results == []

    def test_logical_path_includes_eml_name(self, tmp_path, sample_eml):
        out = str(tmp_path / "out")
        os.makedirs(out)
        results = container_exploder.explode_container(sample_eml, out)
        eml_name = os.path.basename(sample_eml)
        _, _, logical_path = results[0]
        assert logical_path.startswith(eml_name)


# ---------------------------------------------------------------------------
# get_file_type helper
# ---------------------------------------------------------------------------

class TestGetFileType:

    def test_pdf_extension(self):
        assert container_exploder.get_file_type("doc.PDF") == ".pdf"

    def test_case_insensitive(self):
        assert container_exploder.get_file_type("archive.ZIP") == ".zip"

    def test_no_extension(self):
        assert container_exploder.get_file_type("README") == ""
