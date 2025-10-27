#!/usr/bin/env python3
"""
mnemo_report.py — Count IA-32 instruction mnemonics from objdump output and
annotate (year, microarchitecture) up to Pentium II.

Usage:
  objdump -d -M intel a.out | python3 mnemo_report.py
  python3 mnemo_report.py path/to/objdump_output.txt
  ... | python3 mnemo_report.py --sort=count

Notes:
- Requires Intel syntax (objdump -M intel).
- Includes aliases like `je` (alias of `jz`) and `jne` (alias of `jnz`)
- Handles combining mnemonics like `pause` (rep; nop) that are valid on older processors
- Unknown instructions get '?' for year and microarch.
"""

import argparse
import re
import sys
from collections import Counter
from collections.abc import Iterable


# ---------- Known microarchitectures (up to Pentium II) ----------
UARCH: dict[str, tuple[str, str]] = {
    "8086": ("1978", "8086"),
    "80286": ("1982", "80286"),
    "80386": ("1985", "80386"),
    "80486": ("1989", "80486"),
    "Pentium": ("1993", "Pentium (P5)"),
    "PentiumMMX": ("1997", "Pentium MMX"),
    "PentiumPro": ("1995", "Pentium Pro (P6)"),
    "PentiumII": ("1997", "Pentium II (P6)"),
}

# ---------- Combining mnemonics ----------
# These are instruction sequences recognized by disassemblers as single mnemonics
# but are actually valid combinations of older instructions. We annotate with the
# year/uarch when the mnemonic was introduced, but note the compatibility.
COMBINING_MNEMONICS: dict[str, tuple[str, str, str]] = {
    # mnemonic: (introduced_year, introduced_uarch, note)
    "pause": ("2000", "Pentium 4", "rep nop; compat: 8086"),
}

# ---------- Mnemonic → (year, microarch name) ----------
# This is intentionally not exhaustive; unknowns map to ('?','?').
# Sources are well-known generation breakpoints; exact first-shipping years can
# vary by stepping/model—this table aims for practical categorization only.

# 8086 / 8088 (1978) - Integer and control flow
_8086_MNEMONICS = """
    add adc sub sbb cmp test and or xor not neg
    mov xchg lea push pop call ret jmp
    ja jae jb jbe jc jcxz jecxz jrcxz jz jnz
    jg jge jl jle jo jno js jns jp jnp
    nop hlt clc stc cmc cld std cli sti
    inc dec daa das aaa aas aam aad
    sal shl shr sar rol ror rcl rcr
    cbw cwd xlat
    cmps lods stos movs scas
    pushf popf
    lodsb lodsw stosb stosw scasb scasw movsb movsw cmpsb cmpsw
    int into iret int3
    lahf sahf
    lds les
    mul imul div idiv
    in out
""".split()

# 8087 FPU instructions (1980, shipped with 8086 systems)
_8087_MNEMONICS = """
    fld fst fstp fild fist fistp
    fadd fsub fmul fdiv fsubr fdivr
    faddp fsubp fmulp fdivp fsubrp fdivrp
    fiadd fisub fimul fidiv fisubr fidivr
    fcom fcomp fcompp ficom ficomp
    ftst fxam
    fabs fchs
    fsqrt fscale fprem fprem1 frndint fxtract
    fsin fcos fsincos fptan fpatan f2xm1 fyl2x fyl2xp1
    fldz fld1 fldpi fldl2e fldl2t fldlg2 fldln2
    finit fninit fclex fnclex
    fldcw fstcw fnstcw fstsw fnstsw
    fldenv fstenv fnstenv fsave fnsave frstor
    fincstp fdecstp ffree
    fnop fwait fxch
""".split()

# Aliases explicitly included (same vintage as their canonical forms)
_8086_ALIASES = {
    "je": UARCH["8086"],      # alias of jz
    "jne": UARCH["8086"],     # alias of jnz
    "jna": UARCH["8086"],     # alias of jbe
    "jnb": UARCH["8086"],     # alias of jae
    "jnae": UARCH["8086"],    # alias of jb
    "jnbe": UARCH["8086"],    # alias of ja
    "jnc": UARCH["8086"],     # alias of jae
    "jng": UARCH["8086"],     # alias of jle
    "jnge": UARCH["8086"],    # alias of jl
    "jnl": UARCH["8086"],     # alias of jge
    "jnle": UARCH["8086"],    # alias of jg
    "jpe": UARCH["8086"],     # alias of jp
    "jpo": UARCH["8086"],     # alias of jnp
    "setz": UARCH["80386"],   # alias of sete
    "setnz": UARCH["80386"],  # alias of setne
}

# Build the main instruction dictionary
INTRO: dict[str, tuple[str, str]] = (
    {m: UARCH["8086"] for m in _8086_MNEMONICS}
    | {m: UARCH["8086"] for m in _8087_MNEMONICS}
    | _8086_ALIASES
    | {m: UARCH["80286"] for m in """
        enter leave bound arpl
        ins outs insb insw outsb outsw
        pusha popa
        sldt str ltr lldt verr verw
        sgdt lgdt sidt lidt
        sgdtd lgdtd sidtd lidtd
        lar lsl
        """.split()}
    | {m: UARCH["80386"] for m in """
        cdq cwde movsx movzx
        bsf bsr bt bts btr btc
        lss lfs lgs
        shld shrd
        seto setno sets setns sete setne seta setae setb setbe
        setg setge setl setle setp setpe setpo setnp
        pushad popad
        pushfd popfd
        lodsd stosd scasd movsd cmpsd
        fucom fucomp fucompp
        clts
        """.split()}
    | {m: UARCH["80486"] for m in """
        bswap xadd cmpxchg invd wbinvd invlpg
        cpuid
        """.split()}
    | {m: UARCH["Pentium"] for m in """
        rdmsr wrmsr rdtsc
        cmpxchg8b
        """.split()}
    | {m: UARCH["PentiumMMX"] for m in """
        emms movd movq
        packsswb packssdw packuswb
        paddb paddw paddd paddsb paddsw paddusb paddusw
        pand pandn por pxor
        pcmpeqb pcmpeqw pcmpeqd
        pcmpgtb pcmpgtw pcmpgtd
        pmaddwd pmulhw pmullw
        psllw pslld psllq
        psraw psrad
        psrlw psrld psrlq
        psubb psubw psubd psubsb psubsw psubusb psubusw
        punpckhbw punpckhwd punpckhdq
        punpcklbw punpcklwd punpckldq
        """.split()}
    | {m: UARCH["PentiumPro"] for m in """
        cmovo cmovno cmovz cmove cmovnz cmovne cmova cmovae cmovb cmovbe
        cmovg cmovge cmovl cmovle cmovp cmovpe cmovpo cmovs cmovns
        fcmovb fcmovbe fcmove fcmovnb fcmovnbe fcmovne fcmovu fcmovnu
        fcomi fucomi fcomip fucomip
        rdpmc
        ud2 ud1
        """.split()}
    | {m: UARCH["PentiumII"] for m in """
        sysenter sysexit
        """.split()}
)

# Prefixes that should be skipped when extracting the core instruction
PREFIXES = {
    "rep", "repe", "repz", "repne", "repnz", "lock",
    "data16", "data32", "addr16", "addr32",
    "bnd",
}


def normalize_mnemonic(tokens: list[str]) -> tuple[str | None, int]:
    """
    Given a token list starting at the mnemonic/prefix in a disasm line,
    return the normalized mnemonic and how many tokens were consumed.
    """
    i = 0
    # Skip any number of known prefixes
    while i < len(tokens) and tokens[i].lower() in PREFIXES:
        i += 1
    if i >= len(tokens):
        return None, i

    m = tokens[i].lower().rstrip(",")
    return m, i + 1


# Regex to catch typical objdump lines
LINE_RE = re.compile(
    r"""^\s*
        [0-9a-fA-F]+:         # address
        \s+
        (?:[0-9a-fA-F]{2}\s+)+ # bytes (one or more)
        (?P<rest>.*?)$         # the rest (mnemonic and operands)
    """,
    re.VERBOSE,
)


def parse_stream(iter_lines: Iterable[str]) -> Counter[str]:
    """Parse objdump output and count instruction mnemonics."""
    counts: Counter[str] = Counter()
    for line in iter_lines:
        if m := LINE_RE.match(line):
            rest = m.group("rest").strip()
            if not rest:
                continue

            # Tokenize by whitespace; first tokens may include prefixes
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


def lookup_intro(mnemonic: str) -> tuple[str, str]:
    """Look up the introduction year and microarchitecture for a mnemonic.

    Returns (year, microarch) or (year, microarch_with_note) for combining mnemonics.
    """
    m = mnemonic.lower()

    # Check if it's a combining mnemonic first
    if m in COMBINING_MNEMONICS:
        year, uarch, note = COMBINING_MNEMONICS[m]
        return (year, f"{uarch} ({note})")

    # Otherwise look up in standard table
    return INTRO.get(m, ("?", "?"))


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
        help="sort ascending by 'mnemonic' (default) or by 'count'",
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

    rows = []
    for mnem, cnt in counts.items():
        year, arch = lookup_intro(mnem)
        rows.append((mnem, cnt, year, arch))

    if args.sort == "mnemonic":
        rows.sort(key=lambda r: r[0])  # alphabetical
    elif args.sort == "count":
        rows.sort(key=lambda r: (r[1], r[0]))  # by count, then mnemonic
    elif args.sort == "year":
        rows.sort(key=lambda r: (r[2], r[0]))  # by year, then mnemonic
    else:
        raise ValueError(f"unknown column '{args.sort}'")

    # Pretty print as columns
    w_m = max(len("mnemonic"), max((len(r[0]) for r in rows), default=8))
    w_c = max(len("count"), max((len(str(r[1])) for r in rows), default=5))
    w_y = max(len("year"), max((len(r[2]) for r in rows), default=4))
    w_a = max(len("uarch"), max((len(r[3]) for r in rows), default=6))

    header = (
        f"{'mnemonic'.ljust(w_m)}  {'count'.rjust(w_c)}  "
        f"{'year'.ljust(w_y)}  {'uarch'.ljust(w_a)}"
    )
    print(header)
    print("-" * len(header))
    for mnem, cnt, year, arch in rows:
        print(
            f"{mnem.ljust(w_m)}  {str(cnt).rjust(w_c)}  "
            f"{year.ljust(w_y)}  {arch.ljust(w_a)}"
        )


if __name__ == "__main__":
    main()

