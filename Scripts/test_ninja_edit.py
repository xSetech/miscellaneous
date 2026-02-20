#!/usr/bin/env python3
"""Tests for ninja-edit.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Load the module (hyphenated filename requires importlib)
# ---------------------------------------------------------------------------
_SCRIPT = Path(__file__).parent / "ninja-edit.py"
import sys
_spec = importlib.util.spec_from_file_location("ninja_edit", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["ninja_edit"] = _mod  # required for @dataclass to resolve __module__
_spec.loader.exec_module(_mod)

modify_ninja_build = _mod.modify_ninja_build
_target_matches = _mod._target_matches
_split_values = _mod._split_values
main = _mod.main


# ---------------------------------------------------------------------------
# Shared fixture content
# ---------------------------------------------------------------------------
SIMPLE_BUILD = """\
build bin/foo: CXX_EXECUTABLE_LINKER__foo
  FLAGS = -Wall -Wextra
  LINK_LIBRARIES = -lm

build bin/bar: CXX_EXECUTABLE_LINKER__bar
  FLAGS = -O2
  LINK_LIBRARIES = -lc
"""


def write_build(tmp_path: Path, content: str = SIMPLE_BUILD) -> Path:
    p = tmp_path / "build.ninja"
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# _target_matches
# ---------------------------------------------------------------------------
class TestTargetMatches:
    def test_single_match(self):
        assert _target_matches("bin/foo", {"bin/foo"}) == {"bin/foo"}

    def test_no_match(self):
        assert _target_matches("bin/bar", {"bin/foo"}) == set()

    def test_multiple_outputs_first_matches(self):
        assert _target_matches("bin/foo bin/baz", {"bin/foo", "bin/qux"}) == {"bin/foo"}

    def test_multiple_outputs_second_matches(self):
        assert _target_matches("bin/baz bin/foo", {"bin/foo"}) == {"bin/foo"}

    def test_backslash_normalised(self):
        assert _target_matches(r"bin\foo", {"bin/foo"}) == {"bin/foo"}

    def test_empty_targets(self):
        assert _target_matches("bin/foo", set()) == set()


# ---------------------------------------------------------------------------
# _split_values
# ---------------------------------------------------------------------------
class TestSplitValues:
    def test_basic_extraction(self):
        rest, vals = _split_values(
            ["build.ninja", "--targets", "bin/foo", "--var", "FLAGS", "--value", "-g", "-O0"]
        )
        assert vals == ["-g", "-O0"]
        assert "--value" not in rest
        assert "build.ninja" in rest

    def test_terminated_by_known_flag(self):
        rest, vals = _split_values(["--value", "-g", "-O0", "--var", "FLAGS"])
        assert vals == ["-g", "-O0"]
        assert rest == ["--var", "FLAGS"]

    def test_no_value_flag_returns_argv_unchanged(self):
        argv = ["build.ninja", "--targets", "bin/foo", "--var", "FLAGS"]
        rest, vals = _split_values(argv)
        assert vals == []
        assert rest == argv

    def test_single_value(self):
        _, vals = _split_values(["--value", "-lm"])
        assert vals == ["-lm"]

    def test_value_at_end_of_argv(self):
        rest, vals = _split_values(["build.ninja", "--targets", "t", "--var", "V", "--value", "-x"])
        assert vals == ["-x"]
        assert "build.ninja" in rest

    def test_dry_run_flag_terminates_values(self):
        rest, vals = _split_values(["--value", "-g", "--dry-run"])
        assert vals == ["-g"]
        assert "--dry-run" in rest


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------
class TestValidation:
    def test_file_not_found(self, tmp_path):
        r = modify_ninja_build(tmp_path / "missing.ninja", ["bin/foo"], "FLAGS", ["-g"])
        assert not r.success
        assert r.error is not None

    def test_no_targets(self, tmp_path):
        p = write_build(tmp_path)
        r = modify_ninja_build(p, [], "FLAGS", ["-g"])
        assert not r.success
        assert "targets" in r.error.lower()

    def test_no_values(self, tmp_path):
        p = write_build(tmp_path)
        r = modify_ninja_build(p, ["bin/foo"], "FLAGS", [])
        assert not r.success

    def test_unknown_verb(self, tmp_path):
        p = write_build(tmp_path)
        r = modify_ninja_build(p, ["bin/foo"], "FLAGS", ["-g"], verb="replace")
        assert not r.success
        assert "Unknown verb" in r.error


# ---------------------------------------------------------------------------
# Append
# ---------------------------------------------------------------------------
class TestAppend:
    def test_basic_append(self, tmp_path):
        p = write_build(tmp_path)
        r = modify_ninja_build(p, ["bin/foo"], "FLAGS", ["-g", "-O0"], backup=False)
        assert r.success
        assert r.lines_changed == 1
        assert "bin/foo" in r.targets_modified
        assert "FLAGS = -Wall -Wextra -g -O0" in p.read_text()

    def test_append_multiple_targets(self, tmp_path):
        p = write_build(tmp_path)
        r = modify_ninja_build(p, ["bin/foo", "bin/bar"], "FLAGS", ["-g"], backup=False)
        assert r.success
        assert r.lines_changed == 2
        text = p.read_text()
        assert "FLAGS = -Wall -Wextra -g" in text
        assert "FLAGS = -O2 -g" in text

    def test_append_does_not_touch_other_target(self, tmp_path):
        p = write_build(tmp_path)
        modify_ninja_build(p, ["bin/foo"], "FLAGS", ["-g"], backup=False)
        assert "FLAGS = -O2\n" in p.read_text()

    def test_append_single_value(self, tmp_path):
        p = write_build(tmp_path)
        r = modify_ninja_build(p, ["bin/foo"], "LINK_LIBRARIES", ["-lpthread"], backup=False)
        assert r.success
        assert "LINK_LIBRARIES = -lm -lpthread" in p.read_text()

    # --- Duplicate protection -----------------------------------------------

    def test_append_idempotent(self, tmp_path):
        """Second append of the same value is a no-op."""
        p = write_build(tmp_path)
        modify_ninja_build(p, ["bin/foo"], "FLAGS", ["-g", "-O0"], backup=False)
        text_after_first = p.read_text()

        r2 = modify_ninja_build(p, ["bin/foo"], "FLAGS", ["-g", "-O0"], backup=False)
        assert r2.lines_changed == 0
        assert p.read_text() == text_after_first

    def test_append_idempotent_target_not_in_not_found(self, tmp_path):
        """Skipped-duplicate target must not appear in targets_not_found."""
        p = write_build(tmp_path)
        modify_ninja_build(p, ["bin/foo"], "FLAGS", ["-g"], backup=False)
        r2 = modify_ninja_build(p, ["bin/foo"], "FLAGS", ["-g"], backup=False)
        assert "bin/foo" not in r2.targets_not_found

    def test_different_order_is_not_duplicate(self, tmp_path):
        """'-O0 -g' at the end does NOT block appending '-g -O0'."""
        content = SIMPLE_BUILD.replace(
            "FLAGS = -Wall -Wextra", "FLAGS = -Wall -Wextra -O0 -g"
        )
        p = write_build(tmp_path, content)
        r = modify_ninja_build(p, ["bin/foo"], "FLAGS", ["-g", "-O0"], backup=False)
        assert r.lines_changed == 1
        assert "FLAGS = -Wall -Wextra -O0 -g -g -O0" in p.read_text()


# ---------------------------------------------------------------------------
# Remove
# ---------------------------------------------------------------------------
class TestRemove:
    def test_basic_remove(self, tmp_path):
        p = write_build(tmp_path)
        modify_ninja_build(p, ["bin/foo"], "FLAGS", ["-g", "-O0"], backup=False)
        r = modify_ninja_build(p, ["bin/foo"], "FLAGS", ["-g", "-O0"], verb="remove", backup=False)
        assert r.success
        assert r.lines_changed == 1
        assert "FLAGS = -Wall -Wextra\n" in p.read_text()

    def test_remove_not_present_is_noop(self, tmp_path):
        p = write_build(tmp_path)
        original = p.read_text()
        r = modify_ninja_build(p, ["bin/foo"], "FLAGS", ["-g", "-O0"], verb="remove", backup=False)
        assert r.success
        assert r.lines_changed == 0
        assert p.read_text() == original

    def test_remove_wrong_order_is_noop(self, tmp_path):
        """remove only strips an exact suffix; different order does nothing."""
        content = SIMPLE_BUILD.replace(
            "FLAGS = -Wall -Wextra", "FLAGS = -Wall -Wextra -O0 -g"
        )
        p = write_build(tmp_path, content)
        original = p.read_text()
        r = modify_ninja_build(p, ["bin/foo"], "FLAGS", ["-g", "-O0"], verb="remove", backup=False)
        assert r.lines_changed == 0
        assert p.read_text() == original


# ---------------------------------------------------------------------------
# Target / variable not found
# ---------------------------------------------------------------------------
class TestNotFound:
    def test_missing_target_in_targets_not_found(self, tmp_path):
        p = write_build(tmp_path)
        r = modify_ninja_build(p, ["bin/missing"], "FLAGS", ["-g"], backup=False)
        assert r.success
        assert "bin/missing" in r.targets_not_found

    def test_partial_find(self, tmp_path):
        p = write_build(tmp_path)
        r = modify_ninja_build(p, ["bin/foo", "bin/missing"], "FLAGS", ["-g"], backup=False)
        assert "bin/missing" in r.targets_not_found
        assert "bin/foo" in r.targets_modified

    def test_variable_absent_from_target_block(self, tmp_path):
        content = "build bin/foo: PHONY\n\nbuild bin/bar: CXX\n  FLAGS = -O2\n"
        p = write_build(tmp_path, content)
        r = modify_ninja_build(p, ["bin/foo"], "FLAGS", ["-g"], backup=False)
        assert r.lines_changed == 0


# ---------------------------------------------------------------------------
# Dry-run and backup
# ---------------------------------------------------------------------------
class TestDryRunAndBackup:
    def test_dry_run_does_not_write(self, tmp_path):
        p = write_build(tmp_path)
        original = p.read_text()
        r = modify_ninja_build(p, ["bin/foo"], "FLAGS", ["-g"], dry_run=True, backup=False)
        assert r.success
        assert p.read_text() == original

    def test_backup_created_on_change(self, tmp_path):
        p = write_build(tmp_path)
        modify_ninja_build(p, ["bin/foo"], "FLAGS", ["-g"], backup=True)
        assert p.with_suffix(".ninja.bak").exists()

    def test_no_backup_when_disabled(self, tmp_path):
        p = write_build(tmp_path)
        modify_ninja_build(p, ["bin/foo"], "FLAGS", ["-g"], backup=False)
        assert not p.with_suffix(".ninja.bak").exists()

    def test_no_backup_when_no_changes(self, tmp_path):
        p = write_build(tmp_path)
        modify_ninja_build(p, ["bin/missing"], "FLAGS", ["-g"], backup=True)
        assert not p.with_suffix(".ninja.bak").exists()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------
class TestEdgeCases:
    def test_var_equals_no_space(self, tmp_path):
        """Handle both 'VAR = val' and 'VAR=val' styles."""
        content = "build bin/foo: CXX\n  FLAGS=-O2\n"
        p = write_build(tmp_path, content)
        r = modify_ninja_build(p, ["bin/foo"], "FLAGS", ["-g"], backup=False)
        assert r.lines_changed == 1
        assert "FLAGS=-O2 -g" in p.read_text()

    def test_no_trailing_newline(self, tmp_path):
        content = "build bin/foo: CXX\n  FLAGS = -O2"  # no trailing newline
        p = write_build(tmp_path, content)
        r = modify_ninja_build(p, ["bin/foo"], "FLAGS", ["-g"], backup=False)
        assert r.lines_changed == 1
        assert p.read_text().endswith("-O2 -g")

    def test_only_target_block_modified(self, tmp_path):
        p = write_build(tmp_path)
        modify_ninja_build(p, ["bin/bar"], "FLAGS", ["-g"], backup=False)
        text = p.read_text()
        assert "FLAGS = -O2 -g" in text
        assert "FLAGS = -Wall -Wextra\n" in text  # bin/foo untouched

    def test_summary_contains_key_fields(self, tmp_path):
        p = write_build(tmp_path)
        r = modify_ninja_build(p, ["bin/foo"], "FLAGS", ["-g"], backup=False)
        s = r.summary()
        assert "FLAGS" in s
        assert "append" in s
        assert str(p) in s


# ---------------------------------------------------------------------------
# CLI (main)
# ---------------------------------------------------------------------------
class TestCLI:
    def test_cli_append(self, tmp_path):
        p = write_build(tmp_path)
        rc = main([str(p), "--targets", "bin/foo", "--var", "FLAGS",
                   "--value", "-g", "-O0", "--no-backup"])
        assert rc == 0
        assert "FLAGS = -Wall -Wextra -g -O0" in p.read_text()

    def test_cli_remove(self, tmp_path):
        p = write_build(tmp_path)
        modify_ninja_build(p, ["bin/foo"], "FLAGS", ["-g"], backup=False)
        rc = main([str(p), "--targets", "bin/foo", "--var", "FLAGS",
                   "--value", "-g", "--verb", "remove", "--no-backup"])
        assert rc == 0
        assert "FLAGS = -Wall -Wextra\n" in p.read_text()

    def test_cli_dry_run(self, tmp_path):
        p = write_build(tmp_path)
        original = p.read_text()
        rc = main([str(p), "--targets", "bin/foo", "--var", "FLAGS",
                   "--value", "-g", "--dry-run", "--no-backup"])
        assert rc == 0
        assert p.read_text() == original

    def test_cli_targets_file(self, tmp_path):
        p = write_build(tmp_path)
        tf = tmp_path / "targets.txt"
        tf.write_text("bin/foo\n# comment\nbin/bar\n")
        rc = main([str(p), "--targets-file", str(tf), "--var", "FLAGS",
                   "--value", "-g", "--no-backup"])
        assert rc == 0
        text = p.read_text()
        assert "FLAGS = -Wall -Wextra -g" in text
        assert "FLAGS = -O2 -g" in text

    def test_cli_targets_file_not_found(self, tmp_path):
        p = write_build(tmp_path)
        rc = main([str(p), "--targets-file", str(tmp_path / "missing.txt"),
                   "--var", "FLAGS", "--value", "-g"])
        assert rc == 1

    def test_cli_buildfile_after_values_separated_by_flag(self, tmp_path):
        """buildfile positional can follow --value if a known flag appears between them."""
        p = write_build(tmp_path)
        # --dry-run acts as a terminator so str(p) ends up in the positional slot
        rc = main(["--targets", "bin/foo", "--var", "FLAGS",
                   "--value", "-g", "--dry-run", str(p), "--no-backup"])
        assert rc == 0
