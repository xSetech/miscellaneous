#!/usr/bin/env python3
"""
pip_pin - Resolve a requirements file to exact pinned versions (==) using PyPI.

Unlike pip-compile (from pip-tools), this resolves the latest version available
on PyPI regardless of local platform, wheel availability, or Python version.
It does NOT resolve transitive dependencies — only the packages you list.

Dependencies: only `packaging` (ships with pip).

Usage:
    python pip_pin.py requirements-dev.txt
    python pip_pin.py requirements-dev.txt -o requirements-dev.lock
    python pip_pin.py requirements-dev.txt --pre  # include pre-releases
    cat requirements.txt | python pip_pin.py -
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version, InvalidVersion

PYPI_JSON = "https://pypi.org/pypi/{}/json"


def fetch_versions(package: str) -> list[Version]:
    """Fetch all released versions of a package from PyPI."""
    url = PYPI_JSON.format(package)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise SystemExit(f"error: package '{package}' not found on PyPI")
        raise

    versions: list[Version] = []
    for v_str in data["releases"]:
        try:
            versions.append(Version(v_str))
        except InvalidVersion:
            continue  # skip legacy non-PEP-440 versions
    return versions


def resolve(req: Requirement, *, pre: bool = False) -> str:
    """Return a pinned string like 'black==25.1.0' for the given requirement."""
    versions = fetch_versions(req.name)

    specifier: SpecifierSet = req.specifier
    # Filter by specifier; prereleases only if --pre or the specifier itself
    # already references a pre-release (packaging handles this automatically).
    matching = sorted(
        specifier.filter(versions, prereleases=pre),
        reverse=True,
    )
    if not matching:
        raise SystemExit(
            f"error: no version of '{req.name}' satisfies {specifier or '*'}"
        )
    return f"{req.name}=={matching[0]}"


def parse_requirements(lines: list[str]) -> list[Requirement]:
    """Parse requirement lines, ignoring blanks, comments, and options."""
    reqs: list[Requirement] = []
    for raw in lines:
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        reqs.append(Requirement(line))
    return reqs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pin every requirement to the latest matching version on PyPI.",
    )
    parser.add_argument(
        "requirements",
        help="Path to a requirements file, or '-' to read from stdin.",
    )
    parser.add_argument(
        "-o", "--output",
        help="Write output to this file instead of stdout.",
    )
    parser.add_argument(
        "--pre",
        action="store_true",
        help="Include pre-release versions.",
    )
    args = parser.parse_args()

    if args.requirements == "-":
        lines = sys.stdin.read().splitlines()
    else:
        lines = Path(args.requirements).read_text().splitlines()

    reqs = parse_requirements(lines)
    if not reqs:
        raise SystemExit("error: no requirements found")

    pinned: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(resolve, r, pre=args.pre): r for r in reqs}
        for fut in as_completed(futures):
            result = fut.result()  # propagates exceptions
            req = futures[fut]
            pinned[req.name] = result

    # Preserve original order
    output_lines = [pinned[r.name] for r in reqs]
    output = "\n".join(output_lines) + "\n"

    if args.output:
        Path(args.output).write_text(output)
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(output)


if __name__ == "__main__":
    main()

