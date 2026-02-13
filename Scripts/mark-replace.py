#!/usr/bin/env python3
"""
Replace duplicate multi-line text using a single marked reference block.

This script supports two modes:

MODE 1 - Marker-based (default):
    The target file contains exactly one pair of marker lines:

        # --- CORRECTION MARK - START
        <reference text to match and replace everywhere>
        # --- CORRECTION MARK - END

MODE 2 - Reference file:
    Use --reference to specify a separate file containing the text to match.
    The target file must NOT contain START/END markers.

Both modes will:
  1) Extract and print the reference text.
  2) Replace every exact occurrence of that reference text with:

        CORRECTION MARK - COMMON TEXT

Guards:
  - MODE 1: Refuses unless there is exactly ONE START and ONE END marker in order.
  - MODE 2: Refuses if START/END markers are present in the target file.
  - Both modes refuse if the reference text is empty.
  - Both modes refuse if there are no occurrences to replace.

Usage:
  # Marker mode
  python3 mark-replace.py /path/to/file [--dry-run]
  
  # Reference file mode
  python3 mark-replace.py /path/to/file --reference /path/to/reference [--dry-run]

Options:
  --reference FILE    Use external reference file instead of markers
  --dry-run          Show what would be changed without modifying the file

Notes:
  - Matching is exact (byte-for-byte). If duplicates differ in whitespace/newlines,
    they will not be replaced.
  - In marker mode, the marker lines themselves are NOT removed; only the
    in-between text is replaced.
"""

from __future__ import annotations

import sys
from pathlib import Path

START = "# --- CORRECTION MARK - START"
END = "# --- CORRECTION MARK - END"
REPLACEMENT = "CORRECTION MARK - COMMON TEXT"


def die(msg: str, code: int = 2) -> None:
    """Print error message and exit."""
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(code)


def main(argv: list[str]) -> int:
    # Parse arguments
    dry_run = False
    file_path = None
    reference_path = None
    
    i = 1
    while i < len(argv):
        arg = argv[i]
        if arg == "--dry-run":
            dry_run = True
            i += 1
        elif arg == "--reference":
            if i + 1 >= len(argv):
                die("--reference requires a file path argument")
            reference_path = argv[i + 1]
            i += 2
        elif arg.startswith("-"):
            die(f"Unknown option: {arg}")
        elif file_path is None:
            file_path = arg
            i += 1
        else:
            die("Too many arguments")
    
    if file_path is None:
        print(f"Usage: {argv[0]} FILE [--reference REF_FILE] [--dry-run]", file=sys.stderr)
        return 2

    path = Path(file_path)
    if not path.exists():
        die(f"File not found: {path}")
    if not path.is_file():
        die(f"Not a file: {path}")

    # Read target file with original line endings preserved
    with path.open("r", encoding="utf-8", newline="") as f:
        data = f.read()

    # Detect newline style (default to system newline if mixed/absent)
    if "\r\n" in data:
        newline = "\r\n"
    elif "\n" in data:
        newline = "\n"
    else:
        newline = "\n"  # Default for empty/single-line files

    # Determine mode and extract reference text
    if reference_path is not None:
        # MODE 2: Reference file mode
        ref_path = Path(reference_path)
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
                f"Reference file mode requires target file to have NO markers; "
                f"found {start_count} START and {end_count} END markers."
            )
        
        # Read reference file
        with ref_path.open("r", encoding="utf-8", newline="") as f:
            between = f.read()
        
        if not between:
            die("Reference file is empty; refusing to modify the target file.")
        
        mode_desc = f"reference file mode (using {ref_path})"
    else:
        # MODE 1: Marker-based mode
        lines = data.splitlines(keepends=True)

        # Find marker positions
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

        # Extract in-between text (markers excluded)
        between = "".join(lines[s + 1 : e])

        if not between:
            die("In-between text is empty; refusing to modify the file.")
        
        mode_desc = "marker mode"

    # Print reference text to stdout
    # Ensure it ends with a newline for cleanliness
    if between.endswith(("\n", "\r\n")):
        sys.stdout.write(between)
    else:
        sys.stdout.write(between + newline)

    # Count occurrences before replacement
    count = data.count(between)
    
    if count == 0:
        die(
            f"No occurrences of the reference text found in {path}. "
            "Nothing to replace."
        )
    
    # Replace all exact occurrences of the reference text
    # Important: Add newline only if the original between text ended with one
    if between.endswith(("\n", "\r\n")):
        replacement_text = REPLACEMENT + newline
    else:
        replacement_text = REPLACEMENT
    
    new_data = data.replace(between, replacement_text)

    if new_data == data:
        # This should not happen since we already checked count > 0
        die("No replacements made; this should not happen.")

    # Report what will be/was done
    print(f"Mode: {mode_desc}", file=sys.stderr)
    print(f"Found {count} occurrence(s) of the reference text.", file=sys.stderr)
    
    if dry_run:
        print("DRY RUN: File not modified.", file=sys.stderr)
        return 0

    # Write the modified data back, preserving the original newline style
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(new_data)
    
    print(f"Successfully modified {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

