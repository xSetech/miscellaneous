#!/bin/bash

# Usage: ./h5dump_branch.sh [branch_name] [-- pattern1 pattern2 ...]
#
# Creates a parallel branch mirroring the full repo history.
# At each commit, any tracked files matching the given patterns
# get a companion .h5dump file with the h5dump text output.
#
# Default patterns: *.med *.med.ref
#
# Examples:
#   ./h5dump_branch.sh
#   ./h5dump_branch.sh my-branch
#   ./h5dump_branch.sh my-branch -- '*.med' '*.med.ref' '*.h5'

set -euo pipefail

# --- Parse arguments ---
BRANCH="h5dump-history"
PATTERNS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --)
            shift
            PATTERNS=("$@")
            break
            ;;
        *)
            BRANCH="$1"
            shift
            ;;
    esac
done

if [ ${#PATTERNS[@]} -eq 0 ]; then
    PATTERNS=('*.med' '*.med.ref')
fi

echo "Branch:   $BRANCH"
echo "Patterns: ${PATTERNS[*]}"
echo ""

# --- Gather all commits, oldest first ---
ALL_COMMITS=($(git rev-list --reverse HEAD))
TOTAL=${#ALL_COMMITS[@]}

if [ "$TOTAL" -eq 0 ]; then
    echo "No commits found."
    exit 1
fi

echo "Total commits in history: $TOTAL"

# --- Ensure branch doesn't exist ---
if git rev-parse --verify "$BRANCH" &>/dev/null; then
    echo "Error: branch '$BRANCH' already exists. Delete it or choose another name."
    exit 1
fi

# --- Set up a worktree ---
WORKDIR=$(gmktemp -d)
trap 'git worktree remove --force "$WORKDIR" 2>/dev/null; rm -rf "$WORKDIR"' EXIT

# Create orphan branch to start clean
git worktree add --detach "$WORKDIR" "${ALL_COMMITS[0]}" --quiet
pushd "$WORKDIR" > /dev/null
git checkout --orphan "$BRANCH" --quiet
git reset --hard --quiet

popd > /dev/null

# --- Helper: find matching files in a tree ---
find_matching_files() {
    local commit="$1"
    local result=()
    for pat in "${PATTERNS[@]}"; do
        while IFS= read -r f; do
            [ -n "$f" ] && result+=("$f")
        done < <(git ls-tree -r --name-only "$commit" | grep -E "$(echo "$pat" | sed 's/\./\\./g; s/\*/.*/g')$" || true)
    done
    # Deduplicate
    printf '%s\n' "${result[@]}" | sort -u
}

# --- Main loop ---
pushd "$WORKDIR" > /dev/null

for i in "${!ALL_COMMITS[@]}"; do
    COMMIT="${ALL_COMMITS[$i]}"
    SHORT=$(git rev-parse --short "$COMMIT")
    ORIG_MSG=$(git log -1 --pretty=format:'%s' "$COMMIT")
    ORIG_DATE=$(git log -1 --pretty=format:'%aI' "$COMMIT")
    ORIG_AUTHOR_NAME=$(git log -1 --pretty=format:'%an' "$COMMIT")
    ORIG_AUTHOR_EMAIL=$(git log -1 --pretty=format:'%ae' "$COMMIT")

    NUM=$((i+1))

    # Cherry-pick the commit (no-commit so we can augment it)
    git read-tree --reset -u "$COMMIT" 2>/dev/null || {
        # Fallback: hard checkout
        git rm -rf --quiet . 2>/dev/null || true
        git read-tree "$COMMIT"
        git checkout-index -a -f 2>/dev/null || true
    }

    # Find matching files at this commit
    MATCHED_FILES=()
    while IFS= read -r f; do
        [ -n "$f" ] && MATCHED_FILES+=("$f")
    done < <(find_matching_files "$COMMIT")

    DUMP_COUNT=0

    if [ ${#MATCHED_FILES[@]} -gt 0 ]; then
        for MF in "${MATCHED_FILES[@]}"; do
            DUMP_OUT="${MF}.h5dump"
            DUMP_DIR=$(dirname "$DUMP_OUT")
            [ "$DUMP_DIR" != "." ] && mkdir -p "$DUMP_DIR"

            # Extract and dump
            TMPFILE=$(gmktemp --suffix=".$(basename "$MF")")
            if git show "$COMMIT:$MF" > "$TMPFILE" 2>/dev/null; then
                if h5dump "$TMPFILE" > "$DUMP_OUT" 2>&1; then
                    DUMP_COUNT=$((DUMP_COUNT + 1))
                else
                    echo "# h5dump failed for $MF" > "$DUMP_OUT"
                    DUMP_COUNT=$((DUMP_COUNT + 1))
                fi
            fi
            rm -f "$TMPFILE"
        done
    fi

    # Stage everything (original tree + dump files)
    git add -A

    # Progress line
    if [ $DUMP_COUNT -gt 0 ]; then
        echo "[$NUM/$TOTAL] $SHORT: $ORIG_MSG  (+$DUMP_COUNT h5dump files)"
    else
        # Print progress less frequently for commits with no matching files
        if (( NUM % 50 == 0 )) || (( NUM == TOTAL )); then
            echo "[$NUM/$TOTAL] $SHORT: $ORIG_MSG"
        fi
    fi

    # Commit preserving original metadata
    GIT_AUTHOR_NAME="$ORIG_AUTHOR_NAME" \
    GIT_AUTHOR_EMAIL="$ORIG_AUTHOR_EMAIL" \
    GIT_AUTHOR_DATE="$ORIG_DATE" \
    GIT_COMMITTER_DATE="$ORIG_DATE" \
    git commit -m "$ORIG_MSG" \
        --allow-empty --quiet 2>/dev/null || true
done

popd > /dev/null

echo ""
echo "Done! Branch '$BRANCH' created with $TOTAL commits."
echo ""
echo "Useful commands:"
echo "  git log $BRANCH                                # full history"
echo "  git log $BRANCH -- '*.h5dump'                  # only h5dump changes"
echo "  git log -p $BRANCH -- '*.h5dump'               # h5dump diffs over time"
echo "  git diff $BRANCH~1 $BRANCH -- '*.h5dump'       # latest h5dump diff"
echo "  git log --name-only $BRANCH -- '*.med'          # which .med files changed"

