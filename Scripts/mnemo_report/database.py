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


# ---------- Known microarchitectures (up to Skylake) ----------
UARCH: dict[str, UarchInfo] = {
    "8086": UarchInfo("1978", "8086"),
    "80286": UarchInfo("1982", "80286"),
    "80386": UarchInfo("1985", "80386"),
    "80486": UarchInfo("1989", "80486"),
    "Pentium": UarchInfo("1993", "Pentium (P5)"),
    "PentiumMMX": UarchInfo("1997", "Pentium MMX"),
    "PentiumPro": UarchInfo("1995", "Pentium Pro (P6)"),
    "PentiumII": UarchInfo("1997", "Pentium II (P6)"),
    "PentiumIII": UarchInfo("1999", "Pentium III (Katmai)"),
    "Pentium4": UarchInfo("2000", "Pentium 4 (Willamette)"),
    "x86_64": UarchInfo("2003", "AMD64 / x86-64"),
    "Prescott": UarchInfo("2004", "Pentium 4 (Prescott)"),
    "Merom": UarchInfo("2006", "Core 2 (Merom)"),
    "Penryn": UarchInfo("2007", "Core 2 (Penryn)"),
    "Nehalem": UarchInfo("2008", "Core i (Nehalem)"),
    "Westmere": UarchInfo("2010", "Core i (Westmere)"),
    "SandyBridge": UarchInfo("2011", "Sandy Bridge"),
    "Haswell": UarchInfo("2013", "Haswell"),
    "Broadwell": UarchInfo("2014", "Broadwell"),
    "Skylake": UarchInfo("2015", "Skylake"),
}

# ---------- Combining mnemonics ----------
COMBINING_MNEMONICS: dict[str, CombiningInfo] = {
    "pause": CombiningInfo("2000", "Pentium 4", "rep nop; compat: 8086"),
}

# ---------- Mnemonic word lists by generation ----------

_8086_MNEMONICS: list[str] = """
    add adc sub sbb cmp test and or xor not neg
    mov xchg lea push pop call ret retf jmp
    ja jae jb jbe jc jcxz jecxz jrcxz jz jnz
    jg jge jl jle jo jno js jns jp jnp
    nop hlt clc stc cmc cld std cli sti
    inc dec daa das aaa aas aam aad
    sal shl shr sar rol ror rcl rcr
    cbw cwd xlat xlatb
    cmps lods stos movs scas
    loop loope loopne
    pushf popf
    lodsb lodsw stosb stosw scasb scasw movsb movsw cmpsb cmpsw
    int into iret int3
    lahf sahf wait
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
    "fucompi": UARCH["PentiumPro"],
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
    insd outsd iretd
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

# -- Pentium III / SSE (1999) --
_PENTIUM_III_MNEMONICS: list[str] = """
    addss subss mulss divss sqrtss maxss minss rcpss rsqrtss
    addps subps mulps divps sqrtps maxps minps rcpps rsqrtps
    cmpss cmpps comiss ucomiss
    cmpeqss cmpltss cmpless cmpunordss cmpneqss cmpnltss cmpnless cmpordss
    cmpeqps cmpltps cmpleps cmpunordps cmpneqps cmpnltps cmpnleps cmpordps
    cvtsi2ss cvtss2si cvttss2si cvtpi2ps cvtps2pi cvttps2pi
    movss movaps movups movlps movhps movlhps movhlps movmskps
    shufps unpckhps unpcklps
    andps andnps orps xorps
    ldmxcsr stmxcsr fxsave fxrstor
    pmulhuw psadbw pinsrw pextrw pmovmskb pshufw
    pavgb pavgw pminub pmaxub pminsw pmaxsw
    prefetchnta prefetcht0 prefetcht1 prefetcht2
    sfence movntq movntps maskmovq
""".split()

# -- Pentium 4 / SSE2 (2000) --
_PENTIUM_4_MNEMONICS: list[str] = """
    addpd subpd mulpd divpd sqrtpd maxpd minpd
    addsd subsd mulsd divsd sqrtsd maxsd minsd
    cmppd ucomisd comisd
    cmpeqpd cmpltpd cmpleps cmpunordpd cmpneqpd cmpnltpd cmpnleps cmpordpd
    cmpeqsd cmpltsd cmplesd cmpunordsd cmpneqsd cmpnltsd cmpnlesd cmpordsd
    cvtsi2sd cvtsd2si cvttsd2si cvtsd2ss cvtss2sd
    cvtdq2ps cvtps2dq cvttps2dq cvtdq2pd cvtpd2dq cvttpd2dq
    cvtpd2ps cvtps2pd cvtpd2pi cvttpd2pi cvtpi2pd
    movapd movupd movlpd movhpd movmskpd
    shufpd unpckhpd unpcklpd
    andpd andnpd orpd xorpd
    movdqa movdqu movq2dq movdq2q
    paddq psubq pmuludq
    pshufd pshufhw pshuflw
    punpcklqdq punpckhqdq
    clflush lfence mfence
    movntdq movnti movntpd maskmovdqu
""".split()

# -- x86-64 / AMD64 (2003) --
_X86_64_MNEMONICS: list[str] = """
    cdqe cqo movsxd movabs
    syscall sysret
    pushfq popfq
    cmpxchg16b
""".split()

# -- Prescott / SSE3 (2004) --
_PRESCOTT_MNEMONICS: list[str] = """
    movddup movshdup movsldup
    addsubpd addsubps
    haddpd hsubpd haddps hsubps
    lddqu fisttp
    monitor mwait
""".split()

# -- Core 2 Merom / SSSE3 (2006) --
_MEROM_MNEMONICS: list[str] = """
    pshufb phaddw phaddd phaddsw
    phsubw phsubd phsubsw
    pmaddubsw pmulhrsw palignr
    pabsb pabsw pabsd
    psignb psignw psignd
""".split()

# -- Core 2 Penryn / SSE4.1 (2007) --
_PENRYN_MNEMONICS: list[str] = """
    pmulld pmuldq dppd dpps
    blendpd blendps blendvpd blendvps pblendw pblendvb
    insertps extractps
    pinsrb pinsrd pinsrq pextrb pextrd pextrq
    roundpd roundps roundsd roundss
    mpsadbw phminposuw
    pminsb pminsd pminuw pminud
    pmaxsb pmaxsd pmaxuw pmaxud
    pmovsxbw pmovsxbd pmovsxbq pmovsxwd pmovsxwq pmovsxdq
    pmovzxbw pmovzxbd pmovzxbq pmovzxwd pmovzxwq pmovzxdq
    pcmpeqq ptest movntdqa packusdw
""".split()

# -- Nehalem / SSE4.2 (2008) --
_NEHALEM_MNEMONICS: list[str] = """
    pcmpestri pcmpestrm pcmpistri pcmpistrm
    crc32 popcnt
""".split()

# -- Westmere / AES-NI + CLMUL (2010) --
_WESTMERE_MNEMONICS: list[str] = """
    aesdec aesdeclast aesenc aesenclast aesimc aeskeygenassist
    pclmulqdq
""".split()

# -- Sandy Bridge / AVX (2011) --
_SANDY_BRIDGE_MNEMONICS: list[str] = """
    xgetbv xsave xrstor xsaveopt rdtscp
    vaddps vaddpd vaddss vaddsd vsubps vsubpd vsubss vsubsd
    vmulps vmulpd vmulss vmulsd vdivps vdivpd vdivss vdivsd
    vsqrtps vsqrtpd vsqrtss vsqrtsd
    vmaxps vmaxpd vmaxss vmaxsd vminps vminpd vminss vminsd
    vrcpps vrcpss vrsqrtps vrsqrtss
    vcmpps vcmppd vcmpss vcmpsd
    vcomiss vucomiss vcomisd vucomisd
    vcvtsi2ss vcvtsi2sd vcvtss2si vcvtsd2si vcvttss2si vcvttsd2si
    vcvtss2sd vcvtsd2ss
    vcvtdq2ps vcvtps2dq vcvttps2dq vcvtdq2pd vcvtpd2dq vcvttpd2dq
    vcvtpd2ps vcvtps2pd
    vmovaps vmovapd vmovups vmovupd vmovss vmovsd
    vmovdqa vmovdqu vmovlps vmovhps vmovlpd vmovhpd
    vmovlhps vmovhlps vmovmskps vmovmskpd vmovntps vmovntpd vmovntdq
    vmovd vmovq
    vshufps vshufpd vunpckhps vunpcklps vunpckhpd vunpcklpd
    vandps vandpd vandnps vandnpd vorps vorpd vxorps vxorpd
    vblendps vblendpd vblendvps vblendvpd vpblendw vpblendvb
    vinsertps vextractps vinsertf128 vextractf128
    vroundps vroundpd vroundss vroundsd
    vldmxcsr vstmxcsr
    vpand vpandn vpor vpxor
    vpaddb vpaddw vpaddd vpaddq vpsubb vpsubw vpsubd vpsubq
    vpaddsb vpaddsw vpaddusb vpaddusw vpsubsb vpsubsw vpsubusb vpsubusw
    vpmullw vpmulhw vpmulhuw vpmulld vpmuludq vpmuldq vpmaddwd vpmaddubsw
    vpsllw vpslld vpsllq vpsrlw vpsrld vpsrlq vpsraw vpsrad
    vpshufd vpshufhw vpshuflw vpshufb
    vpcmpeqb vpcmpeqw vpcmpeqd vpcmpeqq
    vpcmpgtb vpcmpgtw vpcmpgtd vpcmpgtq
    vpunpcklbw vpunpcklwd vpunpckldq vpunpcklqdq
    vpunpckhbw vpunpckhwd vpunpckhdq vpunpckhqdq
    vpacksswb vpackssdw vpackuswb vpackusdw
    vpinsrb vpinsrw vpinsrd vpinsrq vpextrb vpextrw vpextrd vpextrq
    vpmovmskb vptest
    vpmovsxbw vpmovsxbd vpmovsxbq vpmovsxwd vpmovsxwq vpmovsxdq
    vpmovzxbw vpmovzxbd vpmovzxbq vpmovzxwd vpmovzxwq vpmovzxdq
    vpminsb vpminsd vpminuw vpminud vpmaxsb vpmaxsd vpmaxuw vpmaxud
    vpminub vpmaxub vpminsw vpmaxsw
    vpavgb vpavgw vpsadbw vmpsadbw vphminposuw
    vpabsb vpabsw vpabsd vpsignb vpsignw vpsignd
    vpalignr vpmulhrsw
    vphaddw vphaddd vphaddsw vphsubw vphsubd vphsubsw
    vdppd vdpps
    vmovddup vmovshdup vmovsldup
    vaddsubpd vaddsubps vhaddpd vhsubpd vhaddps vhsubps
    vlddqu
    vpclmulqdq vaesdec vaesdeclast vaesenc vaesenclast vaesimc vaeskeygenassist
    vcrc32 vpopcnt
    vmovntdqa
    vpcmpestri vpcmpestrm vpcmpistri vpcmpistrm
    vmaskmovdqu
    vzeroall vzeroupper
    vpermilps vpermilpd vperm2f128
    vbroadcastss vbroadcastsd vbroadcastf128
    vtestps vtestpd
    vmaskmovps vmaskmovpd
""".split()

# -- Haswell / AVX2 + BMI1 + BMI2 + FMA + ADX (2013) --
_HASWELL_MNEMONICS: list[str] = """
    andn bextr blsi blsmsk blsr tzcnt lzcnt
    bzhi mulx pdep pext rorx sarx shlx shrx
    adcx adox
    vfmadd132ps vfmadd213ps vfmadd231ps
    vfmadd132pd vfmadd213pd vfmadd231pd
    vfmadd132ss vfmadd213ss vfmadd231ss
    vfmadd132sd vfmadd213sd vfmadd231sd
    vfmsub132ps vfmsub213ps vfmsub231ps
    vfmsub132pd vfmsub213pd vfmsub231pd
    vfmsub132ss vfmsub213ss vfmsub231ss
    vfmsub132sd vfmsub213sd vfmsub231sd
    vfnmadd132ps vfnmadd213ps vfnmadd231ps
    vfnmadd132pd vfnmadd213pd vfnmadd231pd
    vfnmadd132ss vfnmadd213ss vfnmadd231ss
    vfnmadd132sd vfnmadd213sd vfnmadd231sd
    vfnmsub132ps vfnmsub213ps vfnmsub231ps
    vfnmsub132pd vfnmsub213pd vfnmsub231pd
    vfnmsub132ss vfnmsub213ss vfnmsub231ss
    vfnmsub132sd vfnmsub213sd vfnmsub231sd
    vfmaddsub132ps vfmaddsub213ps vfmaddsub231ps
    vfmaddsub132pd vfmaddsub213pd vfmaddsub231pd
    vfmsubadd132ps vfmsubadd213ps vfmsubadd231ps
    vfmsubadd132pd vfmsubadd213pd vfmsubadd231pd
    vperm2i128 vinserti128 vextracti128
    vpermps vpermpd vpermq vpermd
    vpbroadcastb vpbroadcastw vpbroadcastd vpbroadcastq
    vbroadcasti128
    vpmaskmovd vpmaskmovq
    vpsllvd vpsllvq vpsrlvd vpsrlvq vpsravd
    vpgatherdd vpgatherdq vpgatherqd vpgatherqq
    vgatherdps vgatherdpd vgatherqps vgatherqpd
    movbe invpcid
""".split()

# -- Broadwell (2014) --
_BROADWELL_MNEMONICS: list[str] = """
    rdseed
""".split()

# -- Skylake (2015) --
_SKYLAKE_MNEMONICS: list[str] = """
    xsavec xsaves clflushopt
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
    | {m: UARCH["PentiumIII"] for m in _PENTIUM_III_MNEMONICS}
    | {m: UARCH["Pentium4"] for m in _PENTIUM_4_MNEMONICS}
    | {m: UARCH["x86_64"] for m in _X86_64_MNEMONICS}
    | {m: UARCH["Prescott"] for m in _PRESCOTT_MNEMONICS}
    | {m: UARCH["Merom"] for m in _MEROM_MNEMONICS}
    | {m: UARCH["Penryn"] for m in _PENRYN_MNEMONICS}
    | {m: UARCH["Nehalem"] for m in _NEHALEM_MNEMONICS}
    | {m: UARCH["Westmere"] for m in _WESTMERE_MNEMONICS}
    | {m: UARCH["SandyBridge"] for m in _SANDY_BRIDGE_MNEMONICS}
    | {m: UARCH["Haswell"] for m in _HASWELL_MNEMONICS}
    | {m: UARCH["Broadwell"] for m in _BROADWELL_MNEMONICS}
    | {m: UARCH["Skylake"] for m in _SKYLAKE_MNEMONICS}
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
