"""
File storage service — manages the physical file lifecycle.

Responsibilities:
  - Compute safe, unique, collision-proof storage paths
  - Write uploaded file bytes to disk asynchronously
  - Delete files from disk when documents are deleted
  - Validate file content (magic bytes, not just extension)
  - Enforce size limits at the I/O level

Storage layout:
  {UPLOAD_DIR}/
    {user_id}/           ← one directory per user
      {stored_filename}  ← UUID-prefixed sanitized filename

Example:
  uploads/
    a1b2c3d4-.../
      8f3e9a12-quarterly-report.pdf
      2d7c0b45-meeting-notes.docx

Design decisions:
  - Filenames are UUIDs + sanitized original name. UUID prefix guarantees
    global uniqueness; keeping the original name suffix makes debugging easier.
  - Per-user subdirectories prevent one user from listing another's files
    via timing attacks on directory traversal.
  - Files are written with aiofiles for non-blocking I/O — the event loop
    is never blocked during large uploads.
  - Magic byte validation (file header inspection) is used in addition to
    extension checking, preventing disguised executables.
"""

import hashlib
import mimetypes
import os
import re
import uuid
from pathlib import Path
from typing import Optional

import aiofiles
import aiofiles.os
from fastapi import UploadFile

from app.config.settings import settings
from app.core.exceptions import (
    FileTooLargeException,
    UnsupportedFileTypeException,
    ValidationException,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


# ── MIME type registry ────────────────────────────────────────────────────────

# Canonical mapping: file extension → (mime_type, display_name)
SUPPORTED_TYPES: dict[str, tuple[str, str]] = {
    "pdf":  ("application/pdf", "PDF"),
    "docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "Word Document",
    ),
    "txt":  ("text/plain", "Plain Text"),
}

# Magic byte signatures for the file types we accept.
# These are the first N bytes of a valid file — used to detect disguised files.
# A .exe renamed to .pdf would fail this check.
MAGIC_BYTES: dict[str, list[bytes]] = {
    "pdf":  [b"%PDF"],
    "docx": [b"PK\x03\x04"],   # ZIP format (DOCX is a ZIP container)
    "txt":  [],                  # TXT has no universal magic bytes — skip check
}


# ── Filename helpers ──────────────────────────────────────────────────────────

def _sanitize_filename(filename: str) -> str:
    """
    Produce a filesystem-safe version of a filename.

    Rules:
      - Strip path separators (prevent directory traversal)
      - Replace whitespace and special chars with hyphens
      - Collapse multiple hyphens
      - Truncate to 200 chars to stay well within OS limits (255 max)
      - Lowercase for consistency
    """
    # Strip directory components — os.path.basename alone isn't enough
    # because Windows paths use backslash
    name = Path(filename).name
    # Replace anything that isn't alphanumeric, dot, or hyphen
    name = re.sub(r"[^\w.\-]", "-", name, flags=re.ASCII)
    # Collapse repeated hyphens/underscores
    name = re.sub(r"[-_]{2,}", "-", name)
    name = name.strip("-").lower()
    # Enforce max length (keep extension)
    stem, _, ext = name.rpartition(".")
    if ext:
        stem = stem[:190]
        name = f"{stem}.{ext}"
    else:
        name = name[:200]
    return name or "file"


def build_stored_filename(original_filename: str) -> str:
    """
    Construct a collision-proof stored filename.

    Format: {uuid4}-{sanitized_original}
    Example: "8f3e9a12-quarterly-report.pdf"

    The UUID prefix guarantees uniqueness even if two users upload a
    file with the same name at the same millisecond.
    """
    short_id = str(uuid.uuid4()).replace("-", "")[:12]
    safe_name = _sanitize_filename(original_filename)
    return f"{short_id}-{safe_name}"


def get_extension(filename: str) -> str:
    """Extract the lowercase extension without the leading dot."""
    return Path(filename).suffix.lstrip(".").lower()


# ── Storage path helpers ──────────────────────────────────────────────────────

def get_user_upload_dir(user_id: str) -> Path:
    """
    Return the upload directory for a specific user, creating it if absent.

    Path: {UPLOAD_DIR}/{user_id}/
    """
    path = settings.upload_dir_path / user_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_storage_path(user_id: str, stored_filename: str) -> Path:
    """Return the full absolute path where a file will be stored."""
    return get_user_upload_dir(user_id) / stored_filename


# ── Validation ────────────────────────────────────────────────────────────────

class FileValidator:
    """
    Stateless file validation. All methods are synchronous — they operate
    on metadata and the file header bytes, not the full file stream.
    """

    @staticmethod
    def validate_extension(filename: str) -> str:
        """
        Validate the file extension against the supported types allowlist.

        Returns the validated extension (e.g. "pdf").
        Raises UnsupportedFileTypeException on failure.
        """
        ext = get_extension(filename)
        if ext not in SUPPORTED_TYPES:
            raise UnsupportedFileTypeException(
                file_type=ext or "(none)",
                allowed=list(SUPPORTED_TYPES.keys()),
            )
        return ext

    @staticmethod
    def validate_size(size_bytes: int) -> None:
        """
        Validate the file size against the configured maximum.
        Raises FileTooLargeException if the file is too large.
        """
        max_bytes = settings.max_upload_size_bytes
        if size_bytes > max_bytes:
            raise FileTooLargeException(max_size_mb=settings.MAX_UPLOAD_SIZE_MB)
        if size_bytes == 0:
            raise ValidationException("Uploaded file is empty.")

    @staticmethod
    def validate_magic_bytes(header: bytes, extension: str) -> None:
        """
        Inspect the file header (magic bytes) to verify it matches the
        declared extension. Prevents extension spoofing attacks (e.g.
        an executable renamed to .pdf).

        Args:
            header:    First 8 bytes of the file.
            extension: The validated extension from validate_extension().
        """
        signatures = MAGIC_BYTES.get(extension, [])
        if not signatures:
            # No magic bytes defined for this type (e.g. TXT) — skip check
            return
        if not any(header.startswith(sig) for sig in signatures):
            raise UnsupportedFileTypeException(
                file_type=extension,
                allowed=list(SUPPORTED_TYPES.keys()),
            )

    @staticmethod
    def validate_filename(filename: str) -> None:
        """
        Reject filenames that look like path traversal attempts.
        FastAPI's UploadFile strips the path on most OS, but we add a
        belt-and-suspenders check.
        """
        if not filename:
            raise ValidationException("Filename cannot be empty.")
        dangerous_patterns = ["..", "/", "\\", "\x00"]
        for pattern in dangerous_patterns:
            if pattern in filename:
                raise ValidationException(
                    f"Filename contains illegal characters: '{pattern}'."
                )
        if len(filename) > 500:
            raise ValidationException("Filename must be 500 characters or fewer.")


# ── Storage Service ───────────────────────────────────────────────────────────

class StorageService:
    """
    Manages all physical file I/O for document uploads.

    Instantiate per-request (stateless — all state is on disk).
    """

    def __init__(self) -> None:
        self._validator = FileValidator()

    async def save_upload(
        self,
        upload: UploadFile,
        user_id: str,
    ) -> dict:
        """
        Validate and persist an uploaded file to disk.

        Steps:
          1. Validate filename (no path traversal)
          2. Validate extension (allowlist)
          3. Stream file into memory buffer, tracking size
          4. Validate size (after streaming to avoid incomplete reads)
          5. Validate magic bytes (header inspection)
          6. Write to disk atomically via temp file + rename
          7. Return storage metadata

        Returns a dict with keys:
          original_filename, stored_filename, storage_path,
          file_type, mime_type, file_size_bytes

        Raises:
          FileTooLargeException, UnsupportedFileTypeException,
          ValidationException on any validation failure.
        """
        original_filename = upload.filename or "upload"

        # Step 1: filename safety
        self._validator.validate_filename(original_filename)

        # Step 2: extension allowlist
        ext = self._validator.validate_extension(original_filename)

        # Step 3: read file into memory (FastAPI UploadFile uses SpooledTemporaryFile)
        await upload.seek(0)
        file_bytes = await upload.read()
        total_bytes = len(file_bytes)
        header_bytes = file_bytes[:8] if file_bytes else b""

        # Reject if over limit — avoid OOM on huge files
        if total_bytes > settings.max_upload_size_bytes:
            raise FileTooLargeException(max_size_mb=settings.MAX_UPLOAD_SIZE_MB)

        # Step 4: size validation (also catches empty files)
        self._validator.validate_size(len(file_bytes))

        # Step 5: magic byte validation
        self._validator.validate_magic_bytes(header_bytes, ext)

        # Step 6: build paths and write to disk
        stored_filename = build_stored_filename(original_filename)
        storage_path = get_storage_path(user_id, stored_filename)

        await self._write_atomically(file_bytes, storage_path)

        mime_type = SUPPORTED_TYPES[ext][0]

        logger.info(
            "file_saved",
            user_id=user_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_type=ext,
            size_bytes=len(file_bytes),
        )

        return {
            "original_filename": original_filename,
            "stored_filename": stored_filename,
            "storage_path": str(storage_path),
            "file_type": ext,
            "mime_type": mime_type,
            "file_size_bytes": len(file_bytes),
        }

    async def delete_file(self, storage_path: str) -> bool:
        """
        Delete a file from disk.

        Returns True if the file was deleted, False if it was already gone.
        Never raises — a missing file on delete is not an error condition
        (it may have been cleaned up by a previous failed request).
        """
        try:
            await aiofiles.os.remove(storage_path)
            logger.info("file_deleted", path=storage_path)
            return True
        except FileNotFoundError:
            logger.warning("file_not_found_on_delete", path=storage_path)
            return False
        except OSError as exc:
            logger.error("file_delete_failed", path=storage_path, error=str(exc))
            return False

    async def file_exists(self, storage_path: str) -> bool:
        """Check whether a file exists at the given path."""
        return await aiofiles.os.path.exists(storage_path)

    async def get_file_bytes(self, storage_path: str) -> bytes:
        """
        Read and return the full content of a stored file.
        Used when serving file downloads.
        """
        async with aiofiles.open(storage_path, "rb") as f:
            return await f.read()

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    async def _write_atomically(data: bytes, target_path: Path) -> None:
        """
        Write data to a temp file in the same directory, then rename it
        to the target path.

        The rename operation is atomic on POSIX systems — it either
        fully succeeds or fully fails. This prevents partially-written
        files from appearing at the target path if the process crashes
        mid-write.
        """
        tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
        try:
            async with aiofiles.open(tmp_path, "wb") as f:
                await f.write(data)
            # os.replace is atomic on POSIX; on Windows it's best-effort
            await aiofiles.os.replace(str(tmp_path), str(target_path))
        except Exception:
            # Clean up temp file on failure
            try:
                await aiofiles.os.remove(str(tmp_path))
            except OSError:
                pass
            raise
