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
MAX_JOBS="${MAX_JOBS:-$(nproc 2>/dev/null || echo 4)}"

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
echo "Parallel: $MAX_JOBS jobs"
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

# --- Create a single temp directory for the entire run ---
TMPDIR_ROOT=$(mktemp -d)
WORKDIR=$(mktemp -d)
trap 'git worktree remove --force "$WORKDIR" 2>/dev/null; rm -rf "$WORKDIR" "$TMPDIR_ROOT"' EXIT

echo "Temp dir: $TMPDIR_ROOT"

# --- Set up a worktree ---
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
    printf '%s\n' "${result[@]}" | sort -u
}

# --- Helper: dump one file (called in parallel) ---
# Args: commit src_path dump_output_path tmpdir
dump_one_file() {
    local commit="$1"
    local src_path="$2"
    local dump_path="$3"
    local tmpdir="$4"

    local basename
    basename=$(basename "$src_path")
    # Use a fixed name based on the source path to get stable h5dump headers
    local stable_name="$tmpdir/$basename"

    local dump_dir
    dump_dir=$(dirname "$dump_path")
    [ "$dump_dir" != "." ] && mkdir -p "$dump_dir"

    if git show "$commit:$src_path" > "$stable_name" 2>/dev/null; then
        if h5dump "$stable_name" > "$dump_path" 2>&1; then
            # Replace the temp path in the header with just the basename
            # h5dump writes: HDF5 "/path/to/tmp/file.med" {
            # We want:       HDF5 "file.med" {
            sed -i "1s|^HDF5 \".*\"|HDF5 \"$basename\"|" "$dump_path"
        else
            echo "# h5dump failed for $src_path" > "$dump_path"
        fi
        rm -f "$stable_name"
    fi
}

export -f dump_one_file
export TMPDIR_ROOT

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

    # Checkout this commit's tree
    git read-tree --reset -u "$COMMIT" 2>/dev/null || {
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
        # Create a per-commit temp subdirectory so parallel jobs don't collide
        COMMIT_TMPDIR="$TMPDIR_ROOT/$COMMIT"
        mkdir -p "$COMMIT_TMPDIR"

        # Run h5dump in parallel
        printf '%s\n' "${MATCHED_FILES[@]}" | \
            xargs -P "$MAX_JOBS" -I{} bash -c \
                'dump_one_file "$1" "$2" "$3" "$4"' _ \
                "$COMMIT" '{}' '{}.h5dump' "$COMMIT_TMPDIR"

        DUMP_COUNT=${#MATCHED_FILES[@]}

        # Clean up per-commit temp dir
        rm -rf "$COMMIT_TMPDIR"
    fi

    # Stage everything
    git add -A

    # Progress
    if [ $DUMP_COUNT -gt 0 ]; then
        echo "[$NUM/$TOTAL] $SHORT: $ORIG_MSG  (+$DUMP_COUNT h5dump files)"
    else
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

