#!/usr/bin/env bash
#
# graft.sh - Stitch together split LKML git repositories into a single history
#
# This script takes multiple git repositories (numbered 1.git through N.git)
# and grafts them together into a single linear history, where each repo's
# root commit becomes a child of the previous repo's tip.
#
# Usage:
#   ./graft.sh [--fresh]
#
# Options:
#   --fresh    Start from a clean clone of the first repository.
#              Use this for the initial run or to reset everything.
#              Without this flag, the script will re-use the existing
#              lkml-stitched directory and re-fetch/re-graft.
#
# Prerequisites:
#   - git-filter-repo must be installed (https://github.com/newren/git-filter-repo)
#   - Repositories must be named 1.git, 2.git, ..., N.git in the parent directory
#
# Background:
#   The Linux Kernel Mailing List archives from https://lore.kernel.org/lkml/
#   are available as git repositories split into epochs. This script combines
#   them into a single searchable history.
#
# Output:
#   Creates/updates the 'lkml-stitched' directory with a 'combined' branch
#   containing the full stitched history.
#

set -euo pipefail

# Parse command-line arguments
FRESH=false
while [[ $# -gt 0 ]]; do
  case $1 in
    --fresh)
      FRESH=true
      shift
      ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    *)
      echo "Error: Unknown option: $1"
      echo "Usage: $0 [--fresh]"
      echo "Run '$0 --help' for more information."
      exit 1
      ;;
  esac
done

# Configuration: Adjust these if your repository numbering differs
FIRST=1
LAST=17

echo "==> Starting LKML repository stitching (repos ${FIRST}-${LAST})"

# 0) Start from a fresh working clone of the first repo (only if --fresh flag is set)
if [ "$FRESH" = true ]; then
  echo "==> Starting from fresh clone..."
  rm -rf lkml-stitched
  git clone "${FIRST}.git" lkml-stitched
else
  echo "==> Using existing lkml-stitched directory..."
  if [ ! -d "lkml-stitched" ]; then
    echo "Error: lkml-stitched directory does not exist."
    echo "Please run with --fresh flag first: $0 --fresh"
    exit 1
  fi
fi

cd lkml-stitched

# Check if we need to reset from a previous filter-repo run
if git show-ref --verify --quiet refs/heads/combined; then
  echo "==> Detected previous run, cleaning up..."
  git branch -D combined 2>/dev/null || true
  for repl in $(git replace -l); do
    git replace -d "$repl" 2>/dev/null || true
  done
fi

# 1) Add the other repos as remotes and fetch all
echo "==> Adding remotes and fetching..."
for n in $(seq $((FIRST+1)) $LAST); do
  if ! git remote get-url r$n &>/dev/null; then
    git remote add r$n "../${n}.git"
  fi
done
git fetch --all --prune -j 8

# 2) The tip we'll stitch onto (starting with repo #1)
prev_tip="$(git rev-parse HEAD)"

# 3) For each subsequent repo: find its branch tip and root commit,
#    then graft the root onto the previous tip
echo "==> Grafting repositories..."
for n in $(seq $((FIRST+1)) $LAST); do
  # Find the main branch in this remote (ignoring HEAD symbolic ref)
  b="$(git for-each-ref --format='%(refname:short)' "refs/remotes/r${n}/" \
       | grep -v "^r${n}/HEAD$" | head -n1)"

  if [ -z "$b" ]; then
    echo "Error: No branch found for remote r${n}"
    echo "Available refs:"
    git for-each-ref --format='  %(refname:short)' "refs/remotes/r${n}/"
    exit 1
  fi

  tip="$(git rev-parse "$b")"
  root="$(git rev-list --max-parents=0 "$b")"

  echo "  Repo ${n}: grafting root ${root:0:12} -> parent ${prev_tip:0:12}"
  git replace --graft "$root" "$prev_tip"

  prev_tip="$tip"
done

# 4) Create a branch pointing at the final tip (before rewrite)
echo "==> Creating combined branch..."
git branch -f combined "$prev_tip"

# 5) Make the replacements permanent via filter-repo
echo "==> Rewriting history (this may take several minutes)..."
git filter-repo --force --refs combined

# 6) Final sanity check
remaining_replacements=$(git replace -l | wc -l)
if [ "$remaining_replacements" -ne 0 ]; then
  echo "Warning: ${remaining_replacements} git replacements still remain"
  git replace -l
fi

echo ""
echo "==> Complete! The 'combined' branch contains the stitched history."
echo "    Repository: $(pwd)"
echo "    Total commits: $(git rev-list --count combined)"
echo ""
echo "To explore the history:"
echo "  cd lkml-stitched"
echo "  git log combined"
echo "  git log --grep='search term' combined"

