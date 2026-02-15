#!/usr/bin/env python3
"""
utf8norm — Git-tracked file UTF-8 normalization utility.

Reads file paths from stdin (one per line) and ensures each eligible,
Git-tracked file is stored as UTF-8 encoded text without a BOM.

Exit codes:
  0  All eligible files processed successfully (no failures).
  1  Failures occurred and NO files were converted.
  2  Partial success (at least one conversion/skip AND at least one failure).
"""

from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

UTF8_BOM = b"\xef\xbb\xbf"

# Ordered list of legacy encodings to try when a file is not valid UTF-8.
# Windows-1252 decodes *every* byte sequence except 0x81/0x8D/0x8F/0x90/0x9D
# so it is last-resort among the strict candidates.
LEGACY_ENCODINGS: list[str] = [
    "iso-8859-1",   # Latin-1: maps every byte 0x00-0xFF — true superset
    "windows-1252", # CP1252: almost every byte, but 5 undefined slots
    "iso-8859-15",  # Latin-9: Euro sign variant of Latin-1
    "macroman",     # Classic Mac OS Western
]

# iso-8859-1 accepts ALL 256 byte values, so it will always "succeed" in
# strict mode.  We label any encoding that can never fail as "best-effort".
_ALWAYS_DECODABLE: frozenset[str] = frozenset({"iso-8859-1", "latin-1"})


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class Outcome(Enum):
    CONVERTED = auto()
    SKIPPED = auto()
    FAILED = auto()


@dataclass
class FileResult:
    path: str
    outcome: Outcome
    reason: str
    original_size: Optional[int] = None
    new_size: Optional[int] = None
    source_encoding: Optional[str] = None
    lossy: bool = False


@dataclass
class Summary:
    total: int = 0
    converted: int = 0
    skipped: int = 0
    failed: int = 0


# ---------------------------------------------------------------------------
# Git helpers (with per-directory caching)
# ---------------------------------------------------------------------------

_repo_root_cache: dict[str, Optional[str]] = {}


def _git_repo_root(directory: str) -> Optional[str]:
    """Return the Git repository root for *directory*, or None."""
    canon = os.path.realpath(directory)
    if canon in _repo_root_cache:
        return _repo_root_cache[canon]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=canon,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            root = result.stdout.strip()
            _repo_root_cache[canon] = root
            return root
    except (subprocess.TimeoutExpired, OSError):
        pass
    _repo_root_cache[canon] = None
    return None


_tracked_cache: dict[tuple[str, str], bool] = {}


def _is_git_tracked(repo_root: str, rel_path: str) -> bool:
    """Check whether *rel_path* (relative to *repo_root*) is tracked."""
    key = (repo_root, rel_path)
    if key in _tracked_cache:
        return _tracked_cache[key]
    try:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", rel_path],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        tracked = result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        tracked = False
    _tracked_cache[key] = tracked
    return tracked


# ---------------------------------------------------------------------------
# Encoding detection
# ---------------------------------------------------------------------------

@dataclass
class DecodeResult:
    text: str
    encoding: str
    lossy: bool
    had_bom: bool = False


def _try_decode_strict(data: bytes, encoding: str) -> Optional[str]:
    """Attempt strict decoding; return decoded text or None."""
    try:
        return data.decode(encoding, errors="strict")
    except (UnicodeDecodeError, LookupError):
        return None


def detect_and_decode(data: bytes) -> DecodeResult:
    """
    Deterministic encoding detection policy:

    1. UTF-8-SIG (UTF-8 with BOM) — strict
    2. UTF-8 — strict
    3. Each encoding in LEGACY_ENCODINGS — strict
       (encodings in _ALWAYS_DECODABLE are labelled best-effort)
    4. Lossy fallback: UTF-8 with replacement characters
    """
    # 1. UTF-8 with BOM
    if data.startswith(UTF8_BOM):
        body = data[len(UTF8_BOM):]
        text = _try_decode_strict(body, "utf-8")
        if text is not None:
            return DecodeResult(text=text, encoding="utf-8-sig", lossy=False, had_bom=True)

    # 2. Plain UTF-8
    text = _try_decode_strict(data, "utf-8")
    if text is not None:
        return DecodeResult(text=text, encoding="utf-8", lossy=False, had_bom=False)

    # 3. Legacy encodings
    for enc in LEGACY_ENCODINGS:
        text = _try_decode_strict(data, enc)
        if text is not None:
            is_besteff = enc.lower().replace("-", "") in {
                e.lower().replace("-", "") for e in _ALWAYS_DECODABLE
            }
            return DecodeResult(
                text=text,
                encoding=enc,
                lossy=is_besteff,  # label always-decodable as best-effort/lossy
                had_bom=False,
            )

    # 4. Lossy fallback
    text = data.decode("utf-8", errors="replace")
    return DecodeResult(text=text, encoding="utf-8(lossy)", lossy=True, had_bom=False)


# ---------------------------------------------------------------------------
# Atomic file write
# ---------------------------------------------------------------------------

def atomic_write(target: Path, data: bytes, mode: int) -> None:
    """Write *data* to *target* atomically, preserving *mode* bits."""
    fd = -1
    tmp_path: Optional[str] = None
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=str(target.parent),
            prefix=f".{target.name}.",
            suffix=".tmp",
        )
        os.write(fd, data)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, str(target))
        tmp_path = None  # successfully replaced — nothing to clean up
    finally:
        if fd >= 0:
            os.close(fd)
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Per-file processing
# ---------------------------------------------------------------------------

def process_file(raw_path: str, *, dry_run: bool = False) -> FileResult:
    """Process a single input path and return a FileResult."""
    p = Path(raw_path)

    # --- Existence / type checks ---
    try:
        # Use lstat so we detect symlinks before following
        st = p.lstat()
    except OSError as exc:
        return FileResult(raw_path, Outcome.FAILED, f"cannot stat: {exc}")

    if stat.S_ISLNK(st.st_mode):
        return FileResult(raw_path, Outcome.SKIPPED, "symlink")

    if not stat.S_ISREG(st.st_mode):
        return FileResult(raw_path, Outcome.FAILED, "not a regular file")

    # --- Git tracking ---
    abs_path = p.resolve()
    parent_dir = str(abs_path.parent)

    repo_root = _git_repo_root(parent_dir)
    if repo_root is None:
        return FileResult(raw_path, Outcome.FAILED, "not inside a Git repository")

    try:
        rel_path = str(abs_path.relative_to(repo_root))
    except ValueError:
        return FileResult(raw_path, Outcome.FAILED, "file is outside the detected repo root")

    if not _is_git_tracked(repo_root, rel_path):
        return FileResult(raw_path, Outcome.FAILED, "not tracked by Git")

    # --- Read file ---
    try:
        data = abs_path.read_bytes()
    except OSError as exc:
        return FileResult(raw_path, Outcome.FAILED, f"read error: {exc}")

    original_size = len(data)

    # --- Detect & decode ---
    dr = detect_and_decode(data)

    # Re-encode to UTF-8 (no BOM)
    new_data = dr.text.encode("utf-8")
    new_size = len(new_data)

    # --- Decide whether a rewrite is needed ---
    if new_data == data:
        return FileResult(
            raw_path, Outcome.SKIPPED,
            "already UTF-8 (no change needed)",
            original_size=original_size,
            new_size=new_size,
            source_encoding=dr.encoding,
        )

    # A rewrite is needed.
    if dry_run:
        lossy_tag = " (lossy)" if dr.lossy else ""
        return FileResult(
            raw_path, Outcome.CONVERTED,
            f"[dry-run] would convert from {dr.encoding}{lossy_tag}",
            original_size=original_size,
            new_size=new_size,
            source_encoding=dr.encoding,
            lossy=dr.lossy,
        )

    # --- Write ---
    try:
        perm_bits = stat.S_IMODE(abs_path.stat().st_mode)
        atomic_write(abs_path, new_data, perm_bits)
    except OSError as exc:
        return FileResult(raw_path, Outcome.FAILED, f"write error: {exc}")

    lossy_tag = " (lossy)" if dr.lossy else ""
    return FileResult(
        raw_path, Outcome.CONVERTED,
        f"converted from {dr.encoding}{lossy_tag}",
        original_size=original_size,
        new_size=new_size,
        source_encoding=dr.encoding,
        lossy=dr.lossy,
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_result(r: FileResult) -> None:
    line = f"  {r.reason}"
    if r.original_size is not None and r.new_size is not None:
        line += f" [{r.original_size} → {r.new_size} bytes]"
    print(f"{r.path}")
    print(line)


def print_summary(s: Summary) -> None:
    print()
    print("--- summary ---")
    print(f"  total:     {s.total}")
    print(f"  converted: {s.converted}")
    print(f"  skipped:   {s.skipped}")
    print(f"  failed:    {s.failed}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="utf8norm",
        description="Normalize Git-tracked files to UTF-8 (no BOM).",
    )
    p.add_argument(
        "-n", "--dry-run",
        action="store_true",
        help="Report actions without writing any changes.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = Summary()

    for line in sys.stdin:
        path = line.strip()
        if not path:
            continue
        summary.total += 1
        result = process_file(path, dry_run=args.dry_run)
        print_result(result)

        match result.outcome:
            case Outcome.CONVERTED:
                summary.converted += 1
            case Outcome.SKIPPED:
                summary.skipped += 1
            case Outcome.FAILED:
                summary.failed += 1

    print_summary(summary)

    # Exit code logic
    if summary.failed == 0:
        return 0
    if summary.converted == 0 and summary.skipped == 0:
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())

