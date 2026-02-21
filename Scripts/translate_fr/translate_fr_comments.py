#!/usr/bin/env python3.12
"""Translate French comments and safe string literals in C source files to English.

Uses argostranslate (offline neural translation) for translation.
Parsing is done with tree-sitter-c for accurate C tokenisation.

Safe to translate:
  - Block and line comments
  - String literals that look like user-visible natural-language messages

NOT touched:
  - Strings in MED_NOM_* defines (HDF5 file-format dataset names)
  - Strings in MED_*_GRP / _PATH / _FIELD_GRP / _TAILLE defines (path constants)
  - Strings containing printf format specifiers (%d, %s, …)
  - Strings shorter than 5 chars or lacking whitespace
  - All macro names, function names, type names (ABI-safe by design)
"""

import argparse
import difflib
import re
import sys
from pathlib import Path

import argostranslate.translate
import tree_sitter_c
from tree_sitter import Language, Parser

# Project root is two levels above this file:
#   tools/translate_fr/translate_fr_comments.py  →  tools/translate_fr/  →  tools/  →  ROOT
_SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = _SCRIPT_DIR.parent.parent

# ---------------------------------------------------------------------------
# Translation cache
# ---------------------------------------------------------------------------
_cache: dict[str, str] = {}


def translate(text: str) -> str:
    """Translate French text to English, with caching."""
    text_stripped = text.strip()
    if not text_stripped:
        return text
    if text_stripped in _cache:
        prefix = text[: len(text) - len(text.lstrip())]
        suffix = text[len(text.rstrip()):]
        return prefix + _cache[text_stripped] + suffix
    result = argostranslate.translate.translate(text_stripped, "fr", "en")
    _cache[text_stripped] = result
    prefix = text[: len(text) - len(text.lstrip())]
    suffix = text[len(text.rstrip()):]
    return prefix + result + suffix


# ---------------------------------------------------------------------------
# French detection
# ---------------------------------------------------------------------------
FRENCH_CHARS = frozenset("àâäéèêëîïôùûüçœæÀÂÄÉÈÊËÎÏÔÙÛÜÇŒÆ")

# Unambiguously French words (not common English words)
_FR_STRONG = re.compile(
    r"""(?<!\w)(
        les|une|des|du|
        sont|ont|sera|seront|
        ni|mais|donc|
        pour|dans|sous|avec|vers|entre|
        qui|que|dont|
        cet|cette|ces|
        mes|nos|notre|votre|leurs?|
        aux|
        tous|toute|toutes|
        elle[s]?|ils|elles|nous|vous|
        non|ainsi|alors|depuis|lors|après|avant|
        même|seul[e]?|
        comme|afin|sinon|
        numéro|nombre|valeur|taille|erreur|
        lecture|écriture|fichier|champ|maillage|noeud|
        maille|famille|groupe|profil|calcul|entité|
        appel|objet|liste|tableau|données|attribut|
        lien|paramètre|dimension|version|pointeur|
        longueur|chaîne|caractère|entier|flottant|
        chemin|méthode|fonction|variable|
        interne|externe|retour|résultat|valide|
        sortie|entrée|identifiant|création|suppression|
        ouverture|fermeture|montage|opération|
        vérification|initialisation|
        quelque|soit|chaque|plusieurs|aucun|aucune|
        nouveau|nouvelle|suivant|précédent|
        contenant|correspondant|associé|associée|utilisé|
        vouloir|pouvoir|devoir|savoir|faire|avoir|être|
        ici|là|voici|voilà|
        lorsque|puisque|tandis|
        préfixe|suffixe|nommé|nommée|appelé|appelée|
        contenu|contenue|attendu|attendue|défini|définie|
        imposé|imposée|bloqué|bloquée
    )(?!\w)""",
    re.IGNORECASE | re.VERBOSE,
)

# Weaker indicators — only count if multiple appear
_FR_WEAK = re.compile(
    r"""(?<!\w)(le|la|un|de|du|et|ou|ce|en|au|ma|sa|ne|si|tu|par|sur|car|il|pas)(?!\w)""",
    re.IGNORECASE,
)


def is_french(text: str) -> bool:
    """Return True if *text* appears to be French.

    Requires either:
    - An accented French character, OR
    - At least one strong French keyword, OR
    - At least two weak French keywords (unlikely in English)
    """
    if not text or not text.strip():
        return False
    if any(c in FRENCH_CHARS for c in text):
        return True
    if _FR_STRONG.search(text):
        return True
    weak_matches = _FR_WEAK.findall(text)
    if len(weak_matches) >= 2:
        return True
    return False


# ---------------------------------------------------------------------------
# Placeholder-based protection
# ---------------------------------------------------------------------------
# §N§ is reliably preserved by argostranslate (§ = section sign U+00A7).
_PH_FMT = "§{}§"
_PH_RE = re.compile(r"§(\d+)§")

# C string escape sequences (two-char sequences in the raw source)
_STRING_ESC_RE = re.compile(
    r'\\[ntrb\\"0]'          # \n \t \r \b \\ \" \0
    r'|\\x[0-9A-Fa-f]{1,2}'  # \xNN hex escapes
    r'|\\[0-7]{1,3}'          # \NNN octal escapes
)

# Printf-style format specifiers — if present in a string, skip translation
_FORMAT_SPEC_RE = re.compile(
    r'%[-+#0 ]*\*?\d*(?:\.\d+)?(?:hh?|ll?|[LzjtqZ])?'  # flags/width/precision/length
    r'[cdieEfgGosuxXpnaA%]'                               # conversion char
    r'|%'                                                  # bare % (split format string)
)

# Code-like tokens in comment text that should pass through untranslated
_COMMENT_CODE_RE = re.compile(
    r'\b[A-Z][A-Z0-9_]{2,}\b'                            # ALL_CAPS: MED_NO_PROFILE, IFORMAT
    r'|\b(?:H5|MED|hdf)\w+\b'                             # HDF5/MED API names
    r'|\b_[a-zA-Z]\w+\b'                                  # _private_vars
    r'|\b\w+\(\)'                                          # function_calls()
    r'|\b\w+\.(?:med|c|h|hdf|hdf5|f|py|txt|log|cfg)\b'   # filenames
)


def _protect(text: str, pattern: re.Pattern) -> tuple[str, list[str]]:
    """Replace *pattern* matches with §N§ placeholders.
    Returns (protected_text, list_of_saved_tokens).
    """
    saved: list[str] = []
    offset = 0  # track existing placeholders to avoid collisions

    # Count existing §N§ markers so we start our numbering after them
    for m in _PH_RE.finditer(text):
        offset = max(offset, int(m.group(1)) + 1)

    def _save(m: re.Match) -> str:
        idx = len(saved) + offset
        saved.append(m.group(0))
        return _PH_FMT.format(idx)

    return pattern.sub(_save, text), saved


def _restore(text: str, saved: list[str], offset: int = 0) -> str:
    """Restore §N§ placeholders to their original tokens."""
    def _repl(m: re.Match) -> str:
        idx = int(m.group(1)) - offset
        return saved[idx] if 0 <= idx < len(saved) else m.group(0)
    return _PH_RE.sub(_repl, text)


# ---------------------------------------------------------------------------
# tree-sitter C parser
# ---------------------------------------------------------------------------
_C_LANGUAGE = Language(tree_sitter_c.language())
_TS_PARSER = Parser(_C_LANGUAGE)


def _macro_name_of(node) -> str | None:
    """Return the identifier name of the enclosing #define/#define-fn, or None."""
    p = node.parent
    while p:
        if p.type in ("preproc_def", "preproc_function_def"):
            for child in p.children:
                if child.type == "identifier":
                    return child.text.decode("utf-8")
        p = p.parent
    return None


def _is_safe_define(macro_name: str | None) -> bool:
    """Return True if a string in #define <macro_name> may be translated."""
    if macro_name is None:
        return True
    if re.match(r"MED_NOM_", macro_name):
        return False
    if re.match(r"MED_.*(?:GRP|PATH|FIELD_GRP|TAILLE)$", macro_name):
        return False
    return True


# ---------------------------------------------------------------------------
# Comment translation
# ---------------------------------------------------------------------------
_BLOCK_LINE_PREFIX = re.compile(r"^(\s*\*+\s?)(.*?)(\s*)$")
# Lines that start with code-like constructs (don't translate)
_CODE_LIKE = re.compile(
    r"^\s*(@param|@return|@brief|\\param|\\return|\\brief"
    r"|#define|#if|#endif|#include"
    r"|\*+/$"           # closing */
    r"|/\*"             # opening /*
    r"|TODO|FIXME|XXX"
    r"|SSCRUTE|ISCRUTE|XSCRUTE"
    r")",
    re.IGNORECASE,
)


def _translate_comment_line(text: str) -> str:
    """Translate one line of comment text, protecting code tokens (§N§ placeholders)."""
    if not is_french(text) or _CODE_LIKE.match(text):
        return text
    # Protect code-like tokens so they pass through argostranslate unmodified
    protected, saved = _protect(text, _COMMENT_CODE_RE)
    if not is_french(protected):
        # After protecting code tokens, no French remains — skip
        return text
    translated = translate(protected)
    return _restore(translated, saved)


def translate_block_comment(comment: str) -> str:
    """Translate text lines within a /* ... */ block comment."""
    if not comment.startswith("/*"):
        return comment
    inner = comment[2:-2]  # strip /* and */
    lines = inner.split("\n")
    new_lines = []
    for line in lines:
        m = _BLOCK_LINE_PREFIX.match(line)
        if m:
            prefix, text, trailing = m.group(1), m.group(2), m.group(3)
            new_text = _translate_comment_line(text)
            new_lines.append(prefix + new_text + trailing)
        else:
            new_lines.append(_translate_comment_line(line))
    return "/*" + "\n".join(new_lines) + "*/"


def translate_line_comment(comment: str) -> str:
    """Translate text within a // ... line comment."""
    newline = ""
    body = comment
    if body.endswith("\n"):
        newline = "\n"
        body = body[:-1]
    if not body.startswith("//"):
        return comment
    text = body[2:]
    sp_m = re.match(r"^(\s*)(.*?)(\s*)$", text, re.DOTALL)
    if sp_m:
        sp, inner, trailing = sp_m.group(1), sp_m.group(2), sp_m.group(3)
        new_inner = _translate_comment_line(inner)
        if new_inner != inner:
            return "//" + sp + new_inner + trailing + newline
    return comment


# ---------------------------------------------------------------------------
# String literal safety (content checks — context is handled by AST inspection)
# ---------------------------------------------------------------------------

def is_safe_string_content(inner: str) -> bool:
    """Return True if the string content looks like translatable natural language."""
    if len(inner) <= 4:
        return False
    # Must have whitespace (space or \t escape) to look like natural language
    if " " not in inner and "\\t" not in inner:
        return False
    if inner.startswith("/") and inner.count("/") > 1:
        return False
    # Skip strings with printf format specifiers — too risky to translate correctly
    if _FORMAT_SPEC_RE.search(inner):
        return False
    # Strip escape seqs; check text remains
    stripped = _STRING_ESC_RE.sub(" ", inner).strip()
    if not stripped:
        return False
    return True


def _translate_string_literal(s: str) -> str:
    """Translate a C string literal if it is French and safe to translate.

    s must be the full literal including surrounding quotes.
    Caller is responsible for ensuring the AST context is safe.
    """
    if not (s.startswith('"') and s.endswith('"') and len(s) >= 2):
        return s
    inner = s[1:-1]
    if not is_safe_string_content(inner):
        return s

    # Build a displayable version for French detection
    displayable = (
        _STRING_ESC_RE.sub(" ", inner)
        .replace('\\"', '"')
        .replace("\\\\", "\\")
    )
    if not is_french(displayable):
        return s

    # Protect C escape sequences before translating so they are preserved verbatim
    protected, saved_esc = _protect(inner, _STRING_ESC_RE)

    # Unescape \" and \\ in whatever remains (so they display correctly to the model)
    display_for_trans = protected.replace('\\"', '"').replace("\\\\", "\\")

    translated = translate(display_for_trans)

    # Re-escape any new " or \ introduced by the translation
    translated = translated.replace("\\", "\\\\").replace('"', '\\"')

    # Restore the original escape sequences (§N§ → \t, \n, etc.)
    result = _restore(translated, saved_esc)

    return '"' + result + '"'


# ---------------------------------------------------------------------------
# tree-sitter-based source processing
# ---------------------------------------------------------------------------

def _collect_translations(
    node, src: bytes, out: list[tuple[int, int, bytes]]
) -> None:
    """Recursively walk tree-sitter nodes, collecting (start, end, new_bytes) replacements."""
    if node.is_error:
        return  # skip subtrees tree-sitter couldn't parse

    ntype = node.type

    if ntype == "comment":
        text = src[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
        new_text = (
            translate_block_comment(text) if text.startswith("/*")
            else translate_line_comment(text)
        )
        if new_text != text:
            out.append((node.start_byte, node.end_byte, new_text.encode("utf-8")))
        return  # comments have no children to recurse into

    if ntype == "string_literal":
        # Skip pieces of a concatenated_string — handled at the parent level
        if node.parent and node.parent.type == "concatenated_string":
            return
        text = src[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
        new_text = _translate_string_literal(text)
        if new_text != text:
            out.append((node.start_byte, node.end_byte, new_text.encode("utf-8")))
        return

    if ntype == "concatenated_string":
        for child in node.children:
            if child.type == "string_literal":
                text = src[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                new_text = _translate_string_literal(text)
                if new_text != text:
                    out.append((child.start_byte, child.end_byte, new_text.encode("utf-8")))
        return

    if ntype == "preproc_arg":
        # String literal in a #define body.
        # Use the macro name (from the AST) to decide whether to translate.
        macro = _macro_name_of(node)
        if _is_safe_define(macro):
            raw = src[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
            stripped = raw.strip()
            # Only handle the simple single-string case: #define NAME "..."
            if stripped.startswith('"') and stripped.endswith('"') and stripped.count('"') == 2:
                q_start = raw.index('"')
                abs_start = node.start_byte + len(raw[:q_start].encode("utf-8"))
                str_text = raw[q_start:]
                new_str = _translate_string_literal(str_text)
                if new_str != str_text:
                    out.append((abs_start, node.end_byte, new_str.encode("utf-8")))
        return  # never recurse into preproc_arg children

    # All other node types: recurse into children
    for child in node.children:
        _collect_translations(child, src, out)


def process_source(source: str) -> tuple[str, int]:
    """Return (new_source, change_count) using tree-sitter for accurate parsing."""
    src = source.encode("utf-8", errors="replace")
    tree = _TS_PARSER.parse(src)

    replacements: list[tuple[int, int, bytes]] = []
    _collect_translations(tree.root_node, src, replacements)

    if not replacements:
        return source, 0

    # Apply in reverse byte order so earlier offsets stay valid
    buf = bytearray(src)
    for start, end, new_bytes in sorted(replacements, key=lambda x: x[0], reverse=True):
        buf[start:end] = new_bytes

    return buf.decode("utf-8", errors="replace"), len(replacements)


# ---------------------------------------------------------------------------
# File processing
# ---------------------------------------------------------------------------

def process_file(filepath: Path, *, dry_run: bool = False) -> int:
    """Process one file.  Returns number of changes made (or that would be made)."""
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"  ERROR reading {filepath}: {e}", file=sys.stderr)
        return 0

    new_source, changes = process_source(source)

    if not changes or new_source == source:
        return 0

    if dry_run:
        diff = difflib.unified_diff(
            source.splitlines(keepends=True),
            new_source.splitlines(keepends=True),
            fromfile=str(filepath),
            tofile=str(filepath) + " (translated)",
            n=2,
        )
        sys.stdout.writelines(diff)
    else:
        try:
            filepath.write_text(new_source, encoding="utf-8")
        except OSError as e:
            print(f"  ERROR writing {filepath}: {e}", file=sys.stderr)
            return 0

    return changes


# ---------------------------------------------------------------------------
# Report loader
# ---------------------------------------------------------------------------

def load_report(report_path: Path) -> list[Path]:
    files: list[Path] = []
    with report_path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^(?:\s*\d+\u2192)?(.*?)\t\d+$", line)
            if m:
                rel = m.group(1).strip()
                files.append(PROJECT_ROOT / rel)
    return files


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="translate_fr_comments.py",
        description=(
            "Translate French comments and string literals in C source files to English.\n"
            "Uses argostranslate (offline) + tree-sitter-c for safe, ABI-preserving translation."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  # Translate all files listed in the default report (writes in-place):
  %(prog)s

  # Dry-run: show unified diffs without writing anything:
  %(prog)s --dry-run

  # Translate specific files only:
  %(prog)s src/ci/_MEDfileOpen.c include/med_err.h

  # Use a custom report and project root:
  %(prog)s --report my_report.tsv --root /path/to/project
""",
    )
    p.add_argument(
        "files",
        nargs="*",
        metavar="FILE",
        help="specific C source files to translate (default: use --report)",
    )
    p.add_argument(
        "--report",
        metavar="TSV",
        default=str(PROJECT_ROOT / "reports" / "fr_files_comments_strings_sorted.tsv"),
        help="TSV report listing files to process (default: %(default)s)",
    )
    p.add_argument(
        "--root",
        metavar="DIR",
        default=str(PROJECT_ROOT),
        help="project root for resolving relative paths in report (default: %(default)s)",
    )
    p.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="show unified diffs of what would change; do not modify files",
    )
    p.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="suppress per-file progress lines (errors are always shown)",
    )
    return p


def main() -> None:
    args = build_parser().parse_args()

    root = Path(args.root)

    if args.files:
        files = [Path(f) if Path(f).is_absolute() else root / f for f in args.files]
    else:
        files = load_report(Path(args.report))
        # Re-root relative paths if --root was overridden
        if args.root != str(PROJECT_ROOT):
            files = [root / f.relative_to(PROJECT_ROOT) for f in files]

    tag = "[DRY RUN] " if args.dry_run else ""
    print(f"{tag}Processing {len(files)} files…", flush=True)
    total_changes = 0
    total_files_changed = 0

    for i, filepath in enumerate(files, 1):
        if not filepath.exists():
            print(f"  [{i}/{len(files)}] MISSING: {filepath}", flush=True)
            continue
        rel = filepath.relative_to(root) if filepath.is_relative_to(root) else filepath
        n = process_file(filepath, dry_run=args.dry_run)
        if n:
            total_changes += n
            total_files_changed += 1
            if not args.quiet:
                print(f"  [{i}/{len(files)}] {n:4d} changes  {rel}", flush=True)
        elif not args.quiet:
            print(f"  [{i}/{len(files)}]    0          {rel}", flush=True)

    summary = f"{tag}Done. {total_files_changed} files {'would be ' if args.dry_run else ''}modified, {total_changes} tokens translated."
    print(f"\n{summary}", flush=True)


if __name__ == "__main__":
    main()
