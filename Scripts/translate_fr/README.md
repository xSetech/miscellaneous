# translate_fr_comments

Translates French comments and string literals in the med-fichier C source tree to English,
using [argostranslate](https://github.com/argosopentech/argos-translate) (offline neural MT)
and [tree-sitter-c](https://github.com/tree-sitter/tree-sitter-c) for accurate C parsing.

## Prerequisites

- **Python 3.12** (the `tree_sitter_c` binding requires ≥ 3.10; 3.12 is what argostranslate
  ships its wheels for in this project)
- The **argostranslate fr → en language pack** must be downloaded once:

```python
import argostranslate.package
argostranslate.package.update_package_index()
available = argostranslate.package.get_available_packages()
pkg = next(p for p in available if p.from_code == "fr" and p.to_code == "en")
argostranslate.package.install_from_path(pkg.download())
```

## Installation

```sh
pip install -r tools/translate_fr/requirements.txt
```

## Usage

```
translate_fr_comments.py [-h] [--report TSV] [--root DIR] [--dry-run] [--quiet] [FILE ...]
```

### Translate all files listed in the default report (in-place):

```sh
python3.12 tools/translate_fr/translate_fr_comments.py
```

### Preview changes without writing (unified diff output):

```sh
python3.12 tools/translate_fr/translate_fr_comments.py --dry-run
```

### Translate specific files only:

```sh
python3.12 tools/translate_fr/translate_fr_comments.py src/ci/_MEDfileOpen.c include/med_err.h
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `FILE …` | *(use report)* | Specific files to translate instead of reading the report |
| `--report TSV` | `reports/fr_files_comments_strings_sorted.tsv` | TSV file listing C sources with French content |
| `--root DIR` | project root | Base directory for resolving relative paths from the report |
| `--dry-run`, `-n` | off | Show unified diffs; do not modify any files |
| `--quiet`, `-q` | off | Suppress per-file progress lines |

## What is (and is not) translated

**Translated:**
- Block comments (`/* … */`) and line comments (`//`)
- String literals that look like user-visible natural-language messages
  (have spaces, no printf format specifiers, longer than 4 chars)
- String values of `MED_ERR_*_MSG` macros and similar non-ABI defines

**Not translated (ABI/format safety):**
- `#define MED_NOM_*` string values — HDF5 dataset name identifiers
- `#define MED_*_GRP` / `_PATH` / `_FIELD_GRP` / `_TAILLE` string values — path constants
- Strings containing `%d`, `%s`, `%ld`, … — printf format specifiers dropped by the MT model
- Strings shorter than 5 characters or without whitespace — likely identifiers or tokens
- All macro names, function names, type names — never altered (ABI preserved by design)

Code-like tokens inside comments (ALL_CAPS identifiers, `_private_vars`, `func()` calls,
filenames like `mesh.med`) are protected with placeholder substitution before translation
and restored afterward.

## How it works

1. Each file is parsed with **tree-sitter-c** to produce an accurate AST.
2. `comment`, `string_literal`, `concatenated_string`, and `preproc_arg` nodes are visited.
3. For `preproc_arg` nodes (i.e., `#define` bodies), the macro name is read from the AST
   to decide whether the string is an ABI identifier (skip) or a message (translate).
4. French text is detected using a two-tier keyword list plus accented-character fast-path.
5. Translations are produced by argostranslate and applied as byte-level replacements so
   byte offsets from tree-sitter remain consistent.
6. The translation cache avoids redundant model calls across repeated strings.
