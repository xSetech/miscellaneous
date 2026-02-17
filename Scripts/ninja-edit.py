#!/usr/bin/env python3
"""
Ninja Build File Modifier
==========================
Appends additional link libraries to specific targets in a Ninja build file.

Usage:
    # CLI usage
    python ninja_link_modifier.py build.ninja --targets bin/foo lib/bar \
                                              --libs -lm -lpthread

    # With a targets file (one target per line)
    python ninja_link_modifier.py build.ninja --targets-file targets.txt \
                                              --libs -lm -lpthread

    # Dry-run mode (preview changes without writing)
    python ninja_link_modifier.py build.ninja --targets bin/foo \
                                              --libs -lm --dry-run

    # Programmatic usage
    from ninja_link_modifier import modify_ninja_build
    result = modify_ninja_build("build.ninja", ["bin/foo"], ["-lm", "-lpthread"])
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
    targets_modified: list[str] = field(default_factory=list)
    targets_not_found: list[str] = field(default_factory=list)
    libs_appended: list[str] = field(default_factory=list)
    lines_changed: int = 0
    success: bool = False
    error: str | None = None

    def summary(self) -> str:
        lines = [f"File: {self.filepath}"]
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
    libs: list[str],
    *,
    dry_run: bool = False,
    backup: bool = True,
) -> ModificationResult:
    """Append *libs* to the LINK_LIBRARIES line for each listed *target*.

    Parameters
    ----------
    filepath:
        Path to the Ninja build file.
    targets:
        Build-output names to search for (e.g. ``["bin/foo", "lib/bar.so"]``).
    libs:
        Library flags to append (e.g. ``["-lm", "-lpthread"]``).
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
        libs_appended=list(libs),
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

    if not libs:
        result.error = "No libraries specified to append."
        log.error(result.error)
        return result

    # Normalise target names (forward-slash, no trailing whitespace)
    target_set: set[str] = {t.strip().replace("\\", "/") for t in targets}

    # --- Read the file -----------------------------------------------------
    original_lines = filepath.read_text(encoding="utf-8").splitlines(keepends=True)

    new_lines: list[str] = []
    remaining_targets: set[str] = set(target_set)  # track what we still need
    looking_for_link_libs: set[str] = set()  # targets whose LINK_LIBRARIES we want
    i = 0

    while i < len(original_lines):
        line = original_lines[i]
        stripped = line.lstrip()

        # 1) Check if this is a "build <output>: ..." line
        m = _BUILD_RE.match(stripped)
        if m:
            matched = _target_matches(m.group(1), remaining_targets)
            if matched:
                looking_for_link_libs = matched
                log.debug("Found target(s) %s at line %d", matched, i + 1)
            else:
                # A different build statement resets the search window
                looking_for_link_libs = set()

        # 2) If we're inside a matched target block, look for LINK_LIBRARIES
        elif looking_for_link_libs and stripped.startswith("LINK_LIBRARIES"):
            libs_str = " ".join(libs)
            # Append libs, preserving the original line ending
            if line.endswith("\n"):
                modified = line.rstrip("\n") + " " + libs_str + "\n"
            else:
                modified = line + " " + libs_str

            new_lines.append(modified)
            result.lines_changed += 1
            for t in looking_for_link_libs:
                result.targets_modified.append(t)
                remaining_targets.discard(t)
            log.info(
                "Modified LINK_LIBRARIES for %s at line %d",
                looking_for_link_libs,
                i + 1,
            )
            looking_for_link_libs = set()
            i += 1
            continue

        # 3) If we hit a blank line or a new statement while looking, reset
        elif looking_for_link_libs and (stripped == "" or stripped.startswith("build ")):
            # The target block ended without a LINK_LIBRARIES line
            log.warning(
                "Target(s) %s had no LINK_LIBRARIES line; skipping.",
                looking_for_link_libs,
            )
            looking_for_link_libs = set()

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
def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Append link libraries to specific targets in a Ninja build file.",
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
        "--libs",
        nargs=argparse.REMAINDER,
        required=True,
        metavar="LIB",
        help="Libraries to append (place last, e.g. --libs -lm -lpthread).",
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
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

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

    # Resolve libs (REMAINDER may include a leading '--'; strip it)
    libs = [x for x in (args.libs or []) if x and x != "--"]
    if not libs:
        log.error("No libraries specified. Place --libs last, e.g.: --libs -lm -lpthread")
        return 1

    result = modify_ninja_build(
        filepath=args.buildfile,
        targets=targets,
        libs=libs,
        dry_run=args.dry_run,
        backup=not args.no_backup,
    )

    print("\n" + result.summary())
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
