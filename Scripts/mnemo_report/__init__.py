"""mnemo_report — Count IA-32 instruction mnemonics from objdump output.

Usage:
  objdump -d -M intel a.out | python3 -m mnemo_report
  python3 -m mnemo_report path/to/objdump_output.txt
  ... | python3 -m mnemo_report --sort=count
"""

from mnemo_report.cli import main
from mnemo_report.database import INTRO, UARCH, UarchInfo, lookup_intro
from mnemo_report.parser import parse_stream

__all__: list[str] = [
    "INTRO",
    "UARCH",
    "UarchInfo",
    "lookup_intro",
    "main",
    "parse_stream",
]
