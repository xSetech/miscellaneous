#!/usr/bin/env python3
"""
Replace duplicate multi-line text blocks.

Two modes:
1. Marker mode: Extract text between # --- CORRECTION MARK - START/END markers
2. Reference mode: Use --reference FILE to specify text to find

Options:
  --reference FILE      Use external file as search pattern
  --replacement FILE    Use file content as replacement (default: "# --- CORRECTION MARK - COMMON TEXT")
  --dry-run            Preview changes without modifying file

Replacement text defaults to "# --- CORRECTION MARK - COMMON TEXT" unless --replacement is provided.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

START = "# --- CORRECTION MARK - START"
END = "# --- CORRECTION MARK - END"
DEFAULT_REPLACEMENT = "# --- CORRECTION MARK - COMMON TEXT"


def die(msg: str, code: int = 2) -> None:
    """Print error message and exit."""
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(code)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replace duplicate multi-line text blocks"
    )
    parser.add_argument("file", help="Target file to modify")
    parser.add_argument(
        "--reference",
        metavar="FILE",
        help="External file containing text to find (instead of markers)",
    )
    parser.add_argument(
        "--replacement",
        metavar="FILE",
        help="File containing replacement text (default: standard correction mark)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview changes without modifying file"
    )

    args = parser.parse_args()

    # Validate target file
    path = Path(args.file)
    if not path.exists():
        die(f"File not found: {path}")
    if not path.is_file():
        die(f"Not a file: {path}")

    # Read target file with original line endings preserved
    with path.open("r", encoding="utf-8", newline="") as f:
        data = f.read()

    # Detect newline style
    if "\r\n" in data:
        newline = "\r\n"
    elif "\n" in data:
        newline = "\n"
    else:
        newline = "\n"

    # Determine search text based on mode
    if args.reference is not None:
        # Reference file mode
        ref_path = Path(args.reference)
        if not ref_path.exists():
            die(f"Reference file not found: {ref_path}")
        if not ref_path.is_file():
            die(f"Not a file: {ref_path}")

        # Check that target file has no markers
        lines = data.splitlines(keepends=True)
        start_count = sum(1 for ln in lines if ln.rstrip("\r\n") == START)
        end_count = sum(1 for ln in lines if ln.rstrip("\r\n") == END)

        if start_count > 0 or end_count > 0:
            die(
                f"Reference mode requires target file to have NO markers; "
                f"found {start_count} START and {end_count} END markers."
            )

        # Read reference file
        with ref_path.open("r", encoding="utf-8", newline="") as f:
            search_text = f.read()

        if not search_text:
            die("Reference file is empty.")

        mode_desc = f"reference mode (using {ref_path})"
    else:
        # Marker mode
        lines = data.splitlines(keepends=True)

        start_idxs = [i for i, ln in enumerate(lines) if ln.rstrip("\r\n") == START]
        end_idxs = [i for i, ln in enumerate(lines) if ln.rstrip("\r\n") == END]

        if len(start_idxs) != 1 or len(end_idxs) != 1:
            die(
                f"Expected exactly one START and one END marker; found "
                f"{len(start_idxs)} START and {len(end_idxs)} END."
            )

        s = start_idxs[0]
        e = end_idxs[0]
        if e <= s:
            die("END marker must appear after START marker.")

        search_text = "".join(lines[s + 1 : e])

        if not search_text:
            die("Text between markers is empty.")

        mode_desc = "marker mode"

    # Print search text to stdout
    if search_text.endswith(("\n", "\r\n")):
        sys.stdout.write(search_text)
    else:
        sys.stdout.write(search_text + newline)

    # Count occurrences
    count = data.count(search_text)

    if count == 0:
        die(f"No occurrences found in {path}.")

    # Determine replacement text
    if args.replacement is not None:
        repl_path = Path(args.replacement)
        if not repl_path.exists():
            die(f"Replacement file not found: {repl_path}")
        if not repl_path.is_file():
            die(f"Not a file: {repl_path}")

        with repl_path.open("r", encoding="utf-8", newline="") as f:
            replacement_text = f.read()

        # Preserve newline behavior of search_text
        if search_text.endswith(("\n", "\r\n")):
            if not replacement_text.endswith(("\n", "\r\n")):
                replacement_text += newline
        else:
            # Remove trailing newline if present
            if replacement_text.endswith("\r\n"):
                replacement_text = replacement_text[:-2]
            elif replacement_text.endswith("\n"):
                replacement_text = replacement_text[:-1]
    else:
        # Use default replacement
        if search_text.endswith(("\n", "\r\n")):
            replacement_text = DEFAULT_REPLACEMENT + newline
        else:
            replacement_text = DEFAULT_REPLACEMENT

    # Perform replacement
    new_data = data.replace(search_text, replacement_text)

    if new_data == data:
        die("No replacements made; this should not happen.")

    # Report
    print(f"Mode: {mode_desc}", file=sys.stderr)
    print(f"Found {count} occurrence(s).", file=sys.stderr)

    if args.dry_run:
        print("DRY RUN: File not modified.", file=sys.stderr)
        return 0

    # Write modified data
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(new_data)

    print(f"Successfully modified {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

