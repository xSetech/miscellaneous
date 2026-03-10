"""Instruction database: IA-32 mnemonics mapped to introduction year and microarchitecture."""

from __future__ import annotations

from typing import NamedTuple


class UarchInfo(NamedTuple):
    """Year and microarchitecture name for an instruction's introduction."""

    year: str
    name: str


class CombiningInfo(NamedTuple):
    """Info for combining mnemonics (instruction sequences recognised as one mnemonic)."""

    year: str
    name: str
    note: str


# ---------- Known microarchitectures (up to Pentium II) ----------
UARCH: dict[str, UarchInfo] = {
    "8086": UarchInfo("1978", "8086"),
    "80286": UarchInfo("1982", "80286"),
    "80386": UarchInfo("1985", "80386"),
    "80486": UarchInfo("1989", "80486"),
    "Pentium": UarchInfo("1993", "Pentium (P5)"),
    "PentiumMMX": UarchInfo("1997", "Pentium MMX"),
    "PentiumPro": UarchInfo("1995", "Pentium Pro (P6)"),
    "PentiumII": UarchInfo("1997", "Pentium II (P6)"),
}

# ---------- Combining mnemonics ----------
COMBINING_MNEMONICS: dict[str, CombiningInfo] = {
    "pause": CombiningInfo("2000", "Pentium 4", "rep nop; compat: 8086"),
}

# ---------- Mnemonic word lists by generation ----------

_8086_MNEMONICS: list[str] = """
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

_8087_MNEMONICS: list[str] = """
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

_8086_ALIASES: dict[str, UarchInfo] = {
    "je": UARCH["8086"],
    "jne": UARCH["8086"],
    "jna": UARCH["8086"],
    "jnb": UARCH["8086"],
    "jnae": UARCH["8086"],
    "jnbe": UARCH["8086"],
    "jnc": UARCH["8086"],
    "jng": UARCH["8086"],
    "jnge": UARCH["8086"],
    "jnl": UARCH["8086"],
    "jnle": UARCH["8086"],
    "jpe": UARCH["8086"],
    "jpo": UARCH["8086"],
    "setz": UARCH["80386"],
    "setnz": UARCH["80386"],
}

_80286_MNEMONICS: list[str] = """
    enter leave bound arpl
    ins outs insb insw outsb outsw
    pusha popa
    sldt str ltr lldt verr verw
    sgdt lgdt sidt lidt
    sgdtd lgdtd sidtd lidtd
    lar lsl
""".split()

_80386_MNEMONICS: list[str] = """
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
""".split()

_80486_MNEMONICS: list[str] = """
    bswap xadd cmpxchg invd wbinvd invlpg
    cpuid
""".split()

_PENTIUM_MNEMONICS: list[str] = """
    rdmsr wrmsr rdtsc
    cmpxchg8b
""".split()

_PENTIUM_MMX_MNEMONICS: list[str] = """
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
""".split()

_PENTIUM_PRO_MNEMONICS: list[str] = """
    cmovo cmovno cmovz cmove cmovnz cmovne cmova cmovae cmovb cmovbe
    cmovg cmovge cmovl cmovle cmovp cmovpe cmovpo cmovs cmovns
    fcmovb fcmovbe fcmove fcmovnb fcmovnbe fcmovne fcmovu fcmovnu
    fcomi fucomi fcomip fucomip
    rdpmc
    ud2 ud1
""".split()

_PENTIUM_II_MNEMONICS: list[str] = """
    sysenter sysexit
""".split()

# ---------- Composed instruction dictionary ----------
INTRO: dict[str, UarchInfo] = (
    {m: UARCH["8086"] for m in _8086_MNEMONICS}
    | {m: UARCH["8086"] for m in _8087_MNEMONICS}
    | _8086_ALIASES
    | {m: UARCH["80286"] for m in _80286_MNEMONICS}
    | {m: UARCH["80386"] for m in _80386_MNEMONICS}
    | {m: UARCH["80486"] for m in _80486_MNEMONICS}
    | {m: UARCH["Pentium"] for m in _PENTIUM_MNEMONICS}
    | {m: UARCH["PentiumMMX"] for m in _PENTIUM_MMX_MNEMONICS}
    | {m: UARCH["PentiumPro"] for m in _PENTIUM_PRO_MNEMONICS}
    | {m: UARCH["PentiumII"] for m in _PENTIUM_II_MNEMONICS}
)

# Prefixes that should be skipped when extracting the core instruction
PREFIXES: frozenset[str] = frozenset({
    "rep", "repe", "repz", "repne", "repnz", "lock",
    "data16", "data32", "addr16", "addr32",
    "bnd",
})

_UNKNOWN: UarchInfo = UarchInfo("?", "?")


def lookup_intro(mnemonic: str) -> UarchInfo:
    """Look up the introduction year and microarchitecture for a mnemonic.

    Returns UarchInfo with year and name. For combining mnemonics the name
    includes a compatibility note.
    """
    m = mnemonic.lower()
    if m in COMBINING_MNEMONICS:
        info = COMBINING_MNEMONICS[m]
        return UarchInfo(info.year, f"{info.name} ({info.note})")
    return INTRO.get(m, _UNKNOWN)
