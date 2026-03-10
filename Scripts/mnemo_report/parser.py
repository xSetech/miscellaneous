"""Parse objdump Intel-syntax output and count instruction mnemonics."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from mnemo_report.database import PREFIXES

# Regex to catch typical objdump lines
LINE_RE: re.Pattern[str] = re.compile(
    r"""^\s*
        [0-9a-fA-F]+:         # address
        \s+
        (?:[0-9a-fA-F]{2}\s+)+ # bytes (one or more)
        (?P<rest>.*?)$         # the rest (mnemonic and operands)
    """,
    re.VERBOSE,
)


def normalize_mnemonic(tokens: list[str]) -> tuple[str | None, int]:
    """Given a token list starting at the mnemonic/prefix in a disasm line,
    return the normalized mnemonic and how many tokens were consumed.
    """
    i = 0
    while i < len(tokens) and tokens[i].lower() in PREFIXES:
        i += 1
    if i >= len(tokens):
        return None, i

    m = tokens[i].lower().rstrip(",")
    return m, i + 1


def parse_stream(iter_lines: Iterable[str]) -> Counter[str]:
    """Parse objdump output and count instruction mnemonics."""
    counts: Counter[str] = Counter()
    for line in iter_lines:
        if match := LINE_RE.match(line):
            rest = match.group("rest").strip()
            if not rest:
                continue

            tokens = rest.split()
            if not tokens:
                continue

            mnemonic, _ = normalize_mnemonic(tokens)
            if not mnemonic:
                continue

            # Filter out artifacts: ".byte", ".string" etc. (when -D used)
            if mnemonic.startswith("."):
                continue

            # Remove trailing ':' in cases where objdump prints pseudo-label tokens
            mnemonic = mnemonic.rstrip(":")

            counts[mnemonic] += 1
    return counts
