"""CLI entry point: argument parsing, sorting, and table formatting."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from typing import NamedTuple

from mnemo_report.database import lookup_intro
from mnemo_report.parser import parse_stream


class InstructionRow(NamedTuple):
    """A single row in the output report."""

    mnemonic: str
    freq: int
    year: str
    uarch: str


def build_rows(counts: Counter[str]) -> list[InstructionRow]:
    """Map mnemonic counts to annotated rows."""
    rows: list[InstructionRow] = []
    for mnem, cnt in counts.items():
        info = lookup_intro(mnem)
        rows.append(InstructionRow(mnemonic=mnem, freq=cnt, year=info.year, uarch=info.name))
    return rows


def sort_rows(rows: list[InstructionRow], key: str) -> list[InstructionRow]:
    """Sort rows by the given column name."""
    if key == "mnemonic":
        return sorted(rows, key=lambda r: r.mnemonic)
    if key == "count":
        return sorted(rows, key=lambda r: (r.freq, r.mnemonic))
    if key == "year":
        return sorted(rows, key=lambda r: (r.year, r.mnemonic))
    raise ValueError(f"unknown sort key '{key}'")


def format_table(rows: list[InstructionRow]) -> str:
    """Format rows as aligned columns. Returns the full table string."""
    if not rows:
        return "No instructions found."

    w_m = max(len("mnemonic"), max(len(r.mnemonic) for r in rows))
    w_c = max(len("count"), max(len(str(r.freq)) for r in rows))
    w_y = max(len("year"), max(len(r.year) for r in rows))
    w_a = max(len("uarch"), max(len(r.uarch) for r in rows))

    header = (
        f"{'mnemonic'.ljust(w_m)}  {'count'.rjust(w_c)}  "
        f"{'year'.ljust(w_y)}  {'uarch'.ljust(w_a)}"
    )
    lines: list[str] = [header, "-" * len(header)]
    for row in rows:
        lines.append(
            f"{row.mnemonic.ljust(w_m)}  {str(row.freq).rjust(w_c)}  "
            f"{row.year.ljust(w_y)}  {row.uarch.ljust(w_a)}"
        )
    return "\n".join(lines)


def main() -> None:
    """Main entry point."""
    ap = argparse.ArgumentParser(
        description="Count IA-32 mnemonics from objdump output."
    )
    ap.add_argument("file", nargs="?", help="objdump output file (default: stdin)")
    ap.add_argument(
        "--sort",
        choices=["mnemonic", "count", "year"],
        default="count",
        help="sort ascending by column (default: count)",
    )
    args = ap.parse_args()

    if args.file:
        with open(args.file, encoding="utf-8", errors="ignore") as f:
            counts = parse_stream(f)
    else:
        counts = parse_stream(sys.stdin)

    if not counts:
        print("No instructions found.")
        return

    rows = build_rows(counts)
    rows = sort_rows(rows, args.sort)
    print(format_table(rows))
