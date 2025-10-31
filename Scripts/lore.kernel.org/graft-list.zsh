#!/usr/bin/env zsh
#
# graft-list.zsh - Stitch together split email list git repositories into a single history
#
# DESCRIPTION:
#   This script takes multiple git repositories (epoch repos numbered e0, e1, e2, ...)
#   that were cloned by clone-list.zsh and grafts them together into a single linear
#   history, where each epoch's root commit becomes a child of the previous epoch's tip.
#
#   The script:
#   1. Discovers all epoch remotes (e0, e1, e2, ...) in the repository
#   2. Validates they form a contiguous sequence from e0
#   3. Uses git-replace to graft each epoch's root to the previous epoch's tip
#   4. Creates a 'combined' branch with the full stitched history
#   5. Makes replacements permanent using git-filter-repo
#
# USAGE:
#   graft-list.zsh [OPTIONS] <list_name>
#
# OPTIONS:
#   --overwrite          Overwrite existing 'combined' branch
#   --dry-run            Show what would be done without making changes
#   -h, --help           Show this help message
#
# EXAMPLES:
#   graft-list.zsh lkml
#   graft-list.zsh --overwrite netdev
#   graft-list.zsh --dry-run linux-kernel
#
# PREREQUISITES:
#   - git-filter-repo must be installed (https://github.com/newren/git-filter-repo)
#   - The list repository must have been created by clone-list.zsh
#   - Epoch remotes must be named e0, e1, e2, ... (contiguous from 0)
#
# NOTES:
#   - This operation rewrites git history and may take several minutes
#   - The original epoch branches remain untouched
#   - Run clone-list.zsh first to set up the repository structure
#
# MORE INFO:
#   https://lore.kernel.org/lkml/_/text/mirror/
#

set -e
setopt LOCAL_OPTIONS
setopt EXTENDED_GLOB

# Configuration variables
OVERWRITE=false
DRY_RUN=false

# Color codes for output
if [[ -t 1 ]]; then
    readonly RED='\033[0;31m'
    readonly YELLOW='\033[1;33m'
    readonly GREEN='\033[0;32m'
    readonly BLUE='\033[0;34m'
    readonly CYAN='\033[0;36m'
    readonly NC='\033[0m' # No Color
else
    readonly RED=''
    readonly YELLOW=''
    readonly GREEN=''
    readonly BLUE=''
    readonly CYAN=''
    readonly NC=''
fi

# Print functions
print_error() {
    print -r -- "${RED}ERROR:${NC} $*" >&2
}

print_warning() {
    print -r -- "${YELLOW}WARNING:${NC} $*" >&2
}

print_info() {
    print -r -- "${BLUE}INFO:${NC} $*"
}

print_success() {
    print -r -- "${GREEN}SUCCESS:${NC} $*"
}

print_step() {
    print -r -- "${CYAN}==>${NC} $*"
}

# Show usage information
show_usage() {
    sed -n '/^# DESCRIPTION:/,/^$/p' "$0" | sed 's/^# \?//'
    sed -n '/^# USAGE:/,/^# MORE INFO:/p' "$0" | sed 's/^# \?//'
}

# Prompt user for confirmation
confirm() {
    local prompt="$1"
    local response
    print -n "$prompt [y/N] "
    read -r response
    [[ "$response" =~ ^[Yy]$ ]]
}

# Get the mode for an epoch from git config
get_epoch_mode() {
    local epoch="$1"
    git config --get "remote.e${epoch}.clone-list-mode" 2>/dev/null || echo ""
}

# Get the mirror URL for an epoch from git config
get_epoch_mirror_url() {
    local epoch="$1"
    git config --get "remote.e${epoch}.clone-list-mirror-url" 2>/dev/null || echo ""
}

# Check for and display any epoch configuration
check_epoch_configuration() {
    local -a epoch_numbers=("$@")
    local has_config=false
    local -a local_epochs
    local -a mirror_epochs

    for epoch in "${epoch_numbers[@]}"; do
        local mode=$(get_epoch_mode "$epoch")
        if [[ "$mode" == "local" ]]; then
            has_config=true
            local_epochs+=($epoch)
        elif [[ "$mode" == "mirror" ]]; then
            has_config=true
            mirror_epochs+=($epoch)
        fi
    done

    if [[ "$has_config" == true ]]; then
        print_warning "\n⚙  Special epoch configuration detected:"

        if (( ${#local_epochs} > 0 )); then
            print_warning "  Local-only epochs: ${local_epochs[*]}"
            print_info "    These epochs use local clones and may not be up-to-date with upstream"
        fi

        if (( ${#mirror_epochs} > 0 )); then
            print_info "  Mirror epochs: ${mirror_epochs[*]}"
            for epoch in "${mirror_epochs[@]}"; do
                local mirror_url=$(get_epoch_mirror_url "$epoch")
                print_info "    e${epoch}: ${mirror_url}"
            done
        fi

        print_info ""
    fi
}

# Check if git-filter-repo is available
check_prerequisites() {
    if ! command -v git-filter-repo &>/dev/null; then
        print_error "git-filter-repo is not installed"
        print_info "Install it from: https://github.com/newren/git-filter-repo"
        print_info "On most systems: pip install git-filter-repo --break-system-packages"
        exit 1
    fi
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --overwrite)
                OVERWRITE=true
                shift
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            -*)
                print_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
            *)
                if [[ -n "$list_name" ]]; then
                    print_error "Too many arguments. Only one list name expected."
                    exit 1
                fi
                list_name="$1"
                shift
                ;;
        esac
    done

    if [[ -z "$list_name" ]]; then
        print_error "Missing required argument: list_name"
        show_usage
        exit 1
    fi
}

# Discover epoch remotes in the repository
discover_epoch_remotes() {
    local -a all_remotes
    local -a epoch_remotes
    local -a epoch_numbers

    # Get all remotes
    all_remotes=(${(f)"$(git remote)"})

    if (( ${#all_remotes} == 0 )); then
        print_error "No remotes found in repository"
        print_info "Have you run clone-list.zsh first?"
        exit 1
    fi

    # Filter for epoch remotes (e0, e1, e2, ...)
    for remote in "${all_remotes[@]}"; do
        if [[ "$remote" =~ ^e([0-9]+)$ ]]; then
            epoch_remotes+=("$remote")
            epoch_numbers+=(${match[1]})
        fi
    done

    if (( ${#epoch_remotes} == 0 )); then
        print_error "No epoch remotes found (expected format: e0, e1, e2, ...)"
        print_info "Available remotes:"
        for remote in "${all_remotes[@]}"; do
            print_info "  - $remote"
        done
        exit 1
    fi

    # Sort epoch numbers numerically
    epoch_numbers=(${(n)epoch_numbers})

    # Verify contiguous sequence starting from 0
    if [[ ${epoch_numbers[1]} != 0 ]]; then
        print_error "Epoch remotes must start from e0, but found: e${epoch_numbers[1]}"
        exit 1
    fi

    local expected=0
    for num in "${epoch_numbers[@]}"; do
        if [[ $num != $expected ]]; then
            print_error "Non-contiguous epoch sequence: expected e${expected}, found e${num}"
            print_info "Available epoch remotes:"
            for remote in "${epoch_remotes[@]}"; do
                print_info "  - $remote"
            done
            exit 1
        fi
        expected=$((expected + 1))
    done

    # Return the epoch numbers array
    print -r -- "${epoch_numbers[@]}"
}

# Get the main branch for a remote
get_remote_branch() {
    local remote="$1"
    local branch

    # Find the main branch (ignoring HEAD symbolic ref)
    branch=$(git for-each-ref --format='%(refname:short)' "refs/remotes/${remote}/" \
             | grep -v "^${remote}/HEAD$" | head -n1)

    if [[ -z "$branch" ]]; then
        print_error "No branch found for remote '$remote'"
        print_info "Available refs for ${remote}:"
        git for-each-ref --format='  %(refname:short)' "refs/remotes/${remote}/"
        exit 1
    fi

    print -r -- "$branch"
}

# Main script
main() {
    local list_name=""

    parse_args "$@"
    check_prerequisites

    print_step "Grafting email list epochs: ${BLUE}${list_name}${NC}"

    # Check if directory exists and is a git repository
    if [[ ! -d "$list_name" ]]; then
        print_error "Directory '$list_name' does not exist"
        print_info "Have you run clone-list.zsh first?"
        exit 1
    fi

    cd "$list_name" || {
        print_error "Failed to enter directory: $list_name"
        exit 1
    }

    if ! git rev-parse --git-dir &>/dev/null; then
        print_error "'$list_name' is not a git repository"
        exit 1
    fi

    print_info "Repository: $(pwd)"

    # Check if 'combined' branch already exists
    if git show-ref --verify --quiet refs/heads/combined; then
        if [[ "$OVERWRITE" == false ]]; then
            print_error "Branch 'combined' already exists"
            print_info "Use --overwrite flag to recreate the branch"
            print_info "Or delete it manually: git branch -D combined"
            exit 1
        fi
        print_warning "Will overwrite existing 'combined' branch"
    fi

    # Discover epoch remotes
    print_step "Discovering epoch remotes..."
    local -a epoch_numbers
    epoch_numbers=($(discover_epoch_remotes))

    local first_epoch=${epoch_numbers[1]}
    local last_epoch=${epoch_numbers[-1]}
    local num_epochs=${#epoch_numbers}

    print_success "Found ${num_epochs} epoch remotes: e${first_epoch} through e${last_epoch}"

    # Check for and display any special configuration
    check_epoch_configuration "${epoch_numbers[@]}"

    if [[ "$DRY_RUN" == true ]]; then
        print_info "\n${CYAN}DRY RUN MODE${NC} - showing what would be done:\n"
        print_info "1. Clean up any existing 'combined' branch and git replacements"
        print_info "2. Start with epoch e${first_epoch} as the base"

        for (( i=first_epoch+1; i<=last_epoch; i++ )); do
            print_info "3. Graft epoch e${i} root onto e$((i-1)) tip"
        done

        print_info "4. Create 'combined' branch at e${last_epoch} tip"
        print_info "5. Rewrite history with git-filter-repo"
        print_info "\nNo changes made. Remove --dry-run to execute."
        exit 0
    fi

    # Confirm before proceeding
    print_info "\nThis will create a 'combined' branch by grafting ${num_epochs} epochs together."
    print_warning "This operation rewrites git history and may take several minutes."

    if ! confirm "Proceed with grafting?"; then
        print_info "Aborted by user"
        exit 0
    fi

    # Clean up from any previous runs
    print_step "Cleaning up previous state..."
    if git show-ref --verify --quiet refs/heads/combined; then
        print_info "Removing existing 'combined' branch"
        git branch -D combined 2>/dev/null || true
    fi

    # Remove any existing git replacements
    local -a existing_replacements
    existing_replacements=(${(f)"$(git replace -l 2>/dev/null || true)"})
    if (( ${#existing_replacements} > 0 )); then
        print_info "Removing ${#existing_replacements} existing git replacements"
        for repl in "${existing_replacements[@]}"; do
            git replace -d "$repl" 2>/dev/null || true
        done
    fi

    # Fetch all remotes to ensure we have latest data
    print_step "Fetching from all remotes..."
    if ! git fetch --all --prune --jobs=8; then
        print_error "Failed to fetch from remotes"
        exit 1
    fi

    # Start grafting process
    print_step "Grafting epochs together..."

    # Get the first epoch's branch and tip
    local first_remote="e${first_epoch}"
    local first_branch=$(get_remote_branch "$first_remote")
    local prev_tip=$(git rev-parse "$first_branch")

    print_info "Starting with epoch ${first_epoch}: ${first_branch} (${prev_tip:0:12})"

    # Graft each subsequent epoch
    for (( i=first_epoch+1; i<=last_epoch; i++ )); do
        local remote="e${i}"
        local branch=$(get_remote_branch "$remote")
        local tip=$(git rev-parse "$branch")
        local root=$(git rev-list --max-parents=0 "$branch")

        print_info "Grafting epoch ${i}: root ${root:0:12} -> parent ${prev_tip:0:12}"

        if ! git replace --graft "$root" "$prev_tip"; then
            print_error "Failed to graft epoch ${i}"
            exit 1
        fi

        prev_tip="$tip"
    done

    # Create the combined branch pointing at the final tip
    print_step "Creating 'combined' branch..."
    git branch -f combined "$prev_tip"

    local total_commits=$(git rev-list --count combined)
    print_success "Combined branch created with ${total_commits} commits (before rewrite)"

    # Make replacements permanent with git-filter-repo
    print_step "Rewriting history to make grafts permanent..."
    print_warning "This may take several minutes depending on repository size..."

    if ! git filter-repo --force --refs combined; then
        print_error "git-filter-repo failed"
        print_info "The 'combined' branch may be in an inconsistent state"
        exit 1
    fi

    # Verify cleanup
    local -a remaining_replacements
    remaining_replacements=(${(f)"$(git replace -l 2>/dev/null || true)"})
    if (( ${#remaining_replacements} > 0 )); then
        print_warning "${#remaining_replacements} git replacements still remain"
        for repl in "${remaining_replacements[@]}"; do
            print_warning "  - $repl"
        done
    fi

    # Final statistics
    local final_commits=$(git rev-list --count combined)
    print_success "\n✓ Grafting complete!"
    print_info "Repository: $(pwd)"
    print_info "Branch: combined"
    print_info "Total commits: ${final_commits}"
    print_info "Epochs grafted: e${first_epoch} through e${last_epoch} (${num_epochs} total)"

    print_info "\nTo explore the grafted history:"
    print_info "  ${CYAN}cd ${list_name}${NC}"
    print_info "  ${CYAN}git log combined${NC}"
    print_info "  ${CYAN}git log --grep='search term' combined${NC}"
    print_info "  ${CYAN}git log --all --oneline --graph${NC}"
}

# Run main function with all arguments
main "$@"
