"""
Unit tests for the storage service — validation, filename sanitization,
magic byte checks. No actual file I/O required.
"""

import pytest

from app.core.exceptions import FileTooLargeException, UnsupportedFileTypeException, ValidationException
from app.services.storage_service import (
    FileValidator,
    _sanitize_filename,
    build_stored_filename,
    get_extension,
)


# ── Filename Sanitization ─────────────────────────────────────────────────────

class TestSanitizeFilename:
    def test_normal_filename_unchanged(self):
        result = _sanitize_filename("report.pdf")
        assert result == "report.pdf"

    def test_spaces_replaced_with_hyphens(self):
        result = _sanitize_filename("my report 2024.pdf")
        assert " " not in result
        assert result.endswith(".pdf")

    def test_uppercase_lowercased(self):
        result = _sanitize_filename("REPORT.PDF")
        assert result == "report.pdf"

    def test_path_traversal_stripped(self):
        result = _sanitize_filename("../../etc/passwd")
        assert ".." not in result
        assert "/" not in result

    def test_windows_path_stripped(self):
        result = _sanitize_filename("C:\\Users\\file.txt")
        # Path.name extracts "file.txt" from a Windows path string
        assert "\\" not in result

    def test_long_filename_truncated(self):
        long_name = "a" * 300 + ".pdf"
        result = _sanitize_filename(long_name)
        assert len(result) <= 205  # 200 stem + 1 dot + 3 ext

    def test_special_chars_replaced(self):
        result = _sanitize_filename("file (copy) [1].pdf")
        assert "(" not in result
        assert "[" not in result


class TestBuildStoredFilename:
    def test_format_has_prefix_and_original(self):
        filename = build_stored_filename("my-report.pdf")
        parts = filename.split("-", 1)
        assert len(parts) == 2
        assert filename.endswith(".pdf")

    def test_two_calls_produce_different_names(self):
        a = build_stored_filename("report.pdf")
        b = build_stored_filename("report.pdf")
        assert a != b


# ── Extension Validation ──────────────────────────────────────────────────────

class TestFileValidatorExtension:
    validator = FileValidator()

    def test_pdf_accepted(self):
        assert self.validator.validate_extension("document.pdf") == "pdf"

    def test_docx_accepted(self):
        assert self.validator.validate_extension("report.docx") == "docx"

    def test_txt_accepted(self):
        assert self.validator.validate_extension("notes.txt") == "txt"

    def test_jpg_rejected(self):
        with pytest.raises(UnsupportedFileTypeException):
            self.validator.validate_extension("photo.jpg")

    def test_exe_rejected(self):
        with pytest.raises(UnsupportedFileTypeException):
            self.validator.validate_extension("virus.exe")

    def test_no_extension_rejected(self):
        with pytest.raises(UnsupportedFileTypeException):
            self.validator.validate_extension("noextension")

    def test_uppercase_extension_handled(self):
        assert self.validator.validate_extension("REPORT.PDF") == "pdf"


# ── Size Validation ───────────────────────────────────────────────────────────

class TestFileValidatorSize:
    validator = FileValidator()

    def test_valid_size_passes(self):
        self.validator.validate_size(1024 * 1024)  # 1 MB — no exception

    def test_zero_size_rejected(self):
        with pytest.raises(ValidationException):
            self.validator.validate_size(0)

    def test_over_limit_rejected(self):
        from app.config.settings import settings
        over_limit = settings.max_upload_size_bytes + 1
        with pytest.raises(FileTooLargeException):
            self.validator.validate_size(over_limit)


# ── Magic Byte Validation ─────────────────────────────────────────────────────

class TestFileValidatorMagicBytes:
    validator = FileValidator()

    def test_valid_pdf_header(self):
        header = b"%PDF-1.7 content..."
        self.validator.validate_magic_bytes(header[:8], "pdf")  # should not raise

    def test_fake_pdf_rejected(self):
        header = b"MZ\x90\x00\x03\x00\x00\x00"  # PE executable header
        with pytest.raises(UnsupportedFileTypeException):
            self.validator.validate_magic_bytes(header, "pdf")

    def test_valid_docx_header(self):
        header = b"PK\x03\x04\x14\x00\x00\x00"  # ZIP/DOCX magic bytes
        self.validator.validate_magic_bytes(header, "docx")  # should not raise

    def test_txt_skips_magic_check(self):
        # TXT has no magic bytes — any content is accepted
        self.validator.validate_magic_bytes(b"hello world", "txt")  # should not raise
        self.validator.validate_magic_bytes(b"\x00\x01\x02\x03", "txt")  # also fine


# ── Filename Safety Check ─────────────────────────────────────────────────────

class TestFileValidatorFilename:
    validator = FileValidator()

    def test_valid_filename_passes(self):
        self.validator.validate_filename("my-report.pdf")  # no exception

    def test_empty_filename_rejected(self):
        with pytest.raises(ValidationException):
            self.validator.validate_filename("")

    def test_path_traversal_rejected(self):
        with pytest.raises(ValidationException):
            self.validator.validate_filename("../etc/passwd")

    def test_null_byte_rejected(self):
        with pytest.raises(ValidationException):
            self.validator.validate_filename("file\x00.pdf")

    def test_very_long_filename_rejected(self):
        with pytest.raises(ValidationException):
            self.validator.validate_filename("a" * 501 + ".pdf")
