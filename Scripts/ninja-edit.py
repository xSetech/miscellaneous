#!/usr/bin/env python3
"""
Ninja Build File Modifier
==========================
Modifies a specific variable for targeted build edges in a Ninja build file.
Supports appending values to and removing values from the end of variable lines.

Usage:
    # Append to LINK_LIBRARIES for specific targets
    python ninja-edit.py build.ninja --targets bin/foo lib/bar \
                                     --var LINK_LIBRARIES \
                                     --value -lm -lpthread

    # Append debug flags to FLAGS (verb defaults to "append")
    python ninja-edit.py build.ninja --targets bin/my_test \
                                     --var FLAGS --value -g -O0

    # Remove previously appended values from FLAGS
    python ninja-edit.py build.ninja --targets bin/my_test \
                                     --var FLAGS --value -g -O0 --verb remove

    # With a targets file (one target per line)
    python ninja-edit.py build.ninja --targets-file targets.txt \
                                     --var LINK_LIBRARIES \
                                     --value -lm -lpthread

    # Dry-run mode (preview changes without writing)
    python ninja-edit.py build.ninja --targets bin/foo \
                                     --var FLAGS --value -g -O0 --dry-run

    # Process substitution for the targets file
    python ninja-edit.py --targets-file <(grep -v lib targets.txt) \
                         --var LINK_LIBRARIES \
                         --value /path/to/libc++.a --dry-run -v build.ninja

    # Programmatic usage
    from ninja_edit import modify_ninja_build
    result = modify_ninja_build("build.ninja", ["bin/foo"], "FLAGS", ["-g", "-O0"])
"""

from __future__ import annotations

import argparse
import logging
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------
@dataclass
class ModificationResult:
    """Summary of all modifications applied to a build file."""
    filepath: str
    targets_requested: list[str]
    var: str = ""
    verb: str = ""
    values: list[str] = field(default_factory=list)
    targets_modified: list[str] = field(default_factory=list)
    targets_not_found: list[str] = field(default_factory=list)
    lines_changed: int = 0
    success: bool = False
    error: str | None = None

    def summary(self) -> str:
        lines = [f"File: {self.filepath}"]
        lines.append(f"  Variable          : {self.var}")
        lines.append(f"  Verb              : {self.verb}")
        lines.append(f"  Values            : {' '.join(self.values)}")
        lines.append(f"  Targets requested : {len(self.targets_requested)}")
        lines.append(f"  Targets modified  : {len(self.targets_modified)}")
        lines.append(f"  Lines changed     : {self.lines_changed}")
        if self.targets_not_found:
            lines.append(f"  Targets NOT found : {self.targets_not_found}")
        if self.error:
            lines.append(f"  ERROR: {self.error}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------
_BUILD_RE = re.compile(r"^build\s+(.+?)\s*:")


def _target_matches(build_outputs: str, targets: set[str]) -> set[str]:
    """Return which requested targets appear in a 'build ...:' output list.

    Ninja build lines can declare multiple outputs separated by spaces, and
    outputs may contain ``$`` escapes.  We do a simple split-on-whitespace
    comparison which covers the vast majority of real-world build files.
    """
    outputs = build_outputs.replace("$ ", " ").split()
    # Normalise to forward-slash for comparison
    normalised = {o.replace("\\", "/") for o in outputs}
    return targets & normalised


def modify_ninja_build(
    filepath: str | Path,
    targets: list[str],
    var: str,
    values: list[str],
    verb: str = "append",
    *,
    dry_run: bool = False,
    backup: bool = True,
) -> ModificationResult:
    """Modify a variable line for each listed *target* in a Ninja build file.

    Parameters
    ----------
    filepath:
        Path to the Ninja build file.
    targets:
        Build-output names to search for (e.g. ``["bin/foo", "lib/bar.so"]``).
    var:
        The Ninja variable name to modify (e.g. ``"FLAGS"``, ``"LINK_LIBRARIES"``).
    values:
        Values to append or remove (e.g. ``["-g", "-O0"]``).
    verb:
        ``"append"`` to add values to the end of the line, or ``"remove"``
        to strip them from the end if present.
    dry_run:
        If ``True``, report what would change without writing the file.
    backup:
        If ``True`` (default), create a ``.bak`` copy before writing.

    Returns
    -------
    ModificationResult
        A summary object describing everything that happened.
    """
    filepath = Path(filepath)
    result = ModificationResult(
        filepath=str(filepath),
        targets_requested=list(targets),
        var=var,
        verb=verb,
        values=list(values),
    )

    # --- Validate inputs ---------------------------------------------------
    if not filepath.exists():
        result.error = f"File not found: {filepath}"
        log.error(result.error)
        return result

    if not targets:
        result.error = "No targets specified."
        log.error(result.error)
        return result

    if not values:
        result.error = "No values specified."
        log.error(result.error)
        return result

    if verb not in ("append", "remove"):
        result.error = f"Unknown verb: {verb!r} (expected 'append' or 'remove')"
        log.error(result.error)
        return result

    # Normalise target names (forward-slash, no trailing whitespace)
    target_set: set[str] = {t.strip().replace("\\", "/") for t in targets}
    values_str = " ".join(values)

    # --- Read the file -----------------------------------------------------
    original_lines = filepath.read_text(encoding="utf-8").splitlines(keepends=True)

    new_lines: list[str] = []
    remaining_targets: set[str] = set(target_set)  # track what we still need
    looking_for_var: set[str] = set()  # targets whose variable line we want
    i = 0

    while i < len(original_lines):
        line = original_lines[i]
        stripped = line.lstrip()

        # 1) Check if this is a "build <output>: ..." line
        m = _BUILD_RE.match(stripped)
        if m:
            matched = _target_matches(m.group(1), remaining_targets)
            if matched:
                looking_for_var = matched
                log.debug("Found target(s) %s at line %d", matched, i + 1)
            else:
                # A different build statement resets the search window
                looking_for_var = set()

        # 2) If we're inside a matched target block, look for the variable
        elif looking_for_var and (
            stripped.startswith(var + " =") or stripped.startswith(var + "=")
        ):
            if verb == "append":
                if line.endswith("\n"):
                    modified = line.rstrip("\n") + " " + values_str + "\n"
                else:
                    modified = line + " " + values_str
            else:  # remove
                suffix = " " + values_str
                content = line.rstrip("\n") if line.endswith("\n") else line
                if content.endswith(suffix):
                    content = content[: -len(suffix)]
                    modified = content + "\n" if line.endswith("\n") else content
                else:
                    log.warning(
                        "Values %r not found at end of %s for %s at line %d; skipping.",
                        values_str, var, looking_for_var, i + 1,
                    )
                    for t in looking_for_var:
                        remaining_targets.discard(t)
                    new_lines.append(line)
                    looking_for_var = set()
                    i += 1
                    continue

            new_lines.append(modified)
            result.lines_changed += 1
            for t in looking_for_var:
                result.targets_modified.append(t)
                remaining_targets.discard(t)
            log.info(
                "%s %s for %s at line %d",
                verb.capitalize() + ("ed" if verb == "append" else "d"),
                var, looking_for_var, i + 1,
            )
            looking_for_var = set()
            i += 1
            continue

        # 3) If we hit a blank line or a new statement while looking, reset
        elif looking_for_var and (stripped == "" or stripped.startswith("build ")):
            # The target block ended without the variable line
            log.warning(
                "Target(s) %s had no %s line; skipping.",
                looking_for_var, var,
            )
            looking_for_var = set()

        new_lines.append(line)
        i += 1

    result.targets_not_found = sorted(remaining_targets)
    if result.targets_not_found:
        log.warning("Targets not found in file: %s", result.targets_not_found)

    # --- Write output ------------------------------------------------------
    if dry_run:
        log.info("[DRY-RUN] No file written.")
        result.success = True
        return result

    if result.lines_changed == 0:
        log.info("No modifications needed; file left unchanged.")
        result.success = True
        return result

    if backup:
        bak = filepath.with_suffix(filepath.suffix + ".bak")
        shutil.copy2(filepath, bak)
        log.info("Backup saved to %s", bak)

    filepath.write_text("".join(new_lines), encoding="utf-8")
    log.info("Wrote modified build file to %s", filepath)
    result.success = True
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

# We split --value out manually before argparse sees the argv.  This is the
# simplest way to allow arbitrary values (including those starting with "-")
# in any argument position without REMAINDER swallowing positional args or
# other flags.


def _split_values(argv: list[str]) -> tuple[list[str], list[str]]:
    """Extract ``--value`` values from *argv*, returning (rest, values).

    Everything between ``--value`` and the next recognised ``--flag`` (or end
    of argv) is treated as a value, regardless of whether it starts with a
    dash.  Recognised flags that terminate the values list:
    ``--targets``, ``--targets-file``, ``--var``, ``--verb``,
    ``--dry-run``, ``--no-backup``, ``-v``, ``--verbose``, ``-h``, ``--help``.
    """
    KNOWN_FLAGS = {
        "--targets", "--targets-file", "--var", "--verb",
        "--dry-run", "--no-backup",
        "-v", "--verbose", "-h", "--help",
    }

    try:
        idx = argv.index("--value")
    except ValueError:
        return argv, []

    before = argv[:idx]
    values: list[str] = []
    rest_after: list[str] = []

    i = idx + 1
    collecting = True
    while i < len(argv):
        if collecting and argv[i] in KNOWN_FLAGS:
            collecting = False
        if collecting:
            values.append(argv[i])
        else:
            rest_after.append(argv[i])
        i += 1

    return before + rest_after, values


def _parse_args(argv: list[str] | None = None) -> tuple[argparse.Namespace, list[str]]:
    raw = argv if argv is not None else sys.argv[1:]
    rest, values = _split_values(raw)

    p = argparse.ArgumentParser(
        description="Modify a variable for specific targets in a Ninja build file.",
        usage=(
            "%(prog)s BUILDFILE (--targets T [T ...] | --targets-file FILE) "
            "--var VAR --value VAL [VAL ...] [--verb {append,remove}] "
            "[--dry-run] [--no-backup] [-v]"
        ),
    )
    p.add_argument("buildfile", help="Path to the Ninja build file (e.g. build.ninja)")
    tgt = p.add_mutually_exclusive_group(required=True)
    tgt.add_argument(
        "--targets",
        nargs="+",
        metavar="TARGET",
        help="One or more build targets to modify.",
    )
    tgt.add_argument(
        "--targets-file",
        metavar="FILE",
        help="Path to a file listing targets (one per line).",
    )
    p.add_argument(
        "--var",
        required=True,
        metavar="VAR",
        help="Ninja variable name to modify (e.g. FLAGS, LINK_LIBRARIES).",
    )
    p.add_argument(
        "--verb",
        choices=["append", "remove"],
        default="append",
        help="Action to perform: append values to end (default), or remove from end.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing the file.",
    )
    p.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip creating a .bak backup of the original file.",
    )
    p.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug-level logging.",
    )

    # If --value was not supplied at all, report it clearly.
    if not values and "--value" not in raw:
        p.error("the following arguments are required: --value")

    args = p.parse_args(rest)
    return args, values


def main(argv: list[str] | None = None) -> int:
    args, values = _parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Resolve target list
    if args.targets_file:
        tf = Path(args.targets_file)
        if not tf.exists():
            log.error("Targets file not found: %s", tf)
            return 1
        targets = [
            line.strip()
            for line in tf.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    else:
        targets = args.targets

    if not values:
        log.error("No values specified after --value.")
        return 1

    result = modify_ninja_build(
        filepath=args.buildfile,
        targets=targets,
        var=args.var,
        values=values,
        verb=args.verb,
        dry_run=args.dry_run,
        backup=not args.no_backup,
    )

    print("\n" + result.summary())
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())

