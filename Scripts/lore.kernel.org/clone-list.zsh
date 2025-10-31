#!/usr/bin/env zsh
#
# clone-list.zsh - Clone and combine email list archives from lore.kernel.org
#
# DESCRIPTION:
#   This script clones email list archives that are split across multiple "epoch"
#   repositories and combines them into a single local git repository. Each email
#   list on lore.kernel.org may have multiple numbered epoch repos (e.g., 0, 1, 2...).
#
#   The script:
#   1. Discovers all valid epoch repos for the given list
#   2. Clones each epoch repo to a temporary location
#   3. Sets up remotes in a unified local repo pointing to the clones
#   4. Fetches all data into the unified repo
#   5. Repoints remotes to upstream URLs
#   6. Cleans up temporary clones
#
# USAGE:
#   clone-list.zsh [OPTIONS] <list_name>
#
# OPTIONS:
#   --skip <epochs>      Comma-separated list of epoch numbers to skip (or "all")
#   --jobs <n>           Maximum parallel fetch jobs (default: 8)
#   --prefix <url>       URL prefix for list archives (default: https://lore.kernel.org/)
#   --max-epoch <n>      Maximum epoch number to check (default: 32)
#   -h, --help           Show this help message
#
# EXAMPLES:
#   clone-list.zsh lkml
#   clone-list.zsh --skip 5,7 linux-kernel
#   clone-list.zsh --jobs 4 netdev
#
# NOTES:
#   - The script is idempotent and can be re-run to fetch new epochs
#   - Requires git to be installed and accessible
#   - Network connectivity to lore.kernel.org is required
#   - Large lists (like lkml) may take considerable time to clone
#
# MORE INFO:
#   https://lore.kernel.org/lkml/_/text/mirror/
#

set -e
setopt LOCAL_OPTIONS
setopt EXTENDED_GLOB

# Constants
readonly LIST_PREFIX_DEFAULT="https://lore.kernel.org/"
readonly MAX_EPOCH_DEFAULT=32
readonly DEFAULT_JOBS=8

# Configuration variables
LIST_PREFIX="${LIST_PREFIX_DEFAULT}"
MAX_EPOCH="${MAX_EPOCH_DEFAULT}"
JOBS="${DEFAULT_JOBS}"
SKIP_EPOCHS=()

# Color codes for output
if [[ -t 1 ]]; then
    readonly RED='\033[0;31m'
    readonly YELLOW='\033[1;33m'
    readonly GREEN='\033[0;32m'
    readonly BLUE='\033[0;34m'
    readonly NC='\033[0m' # No Color
else
    readonly RED=''
    readonly YELLOW=''
    readonly GREEN=''
    readonly BLUE=''
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

# Check if an epoch should be skipped
should_skip_epoch() {
    local epoch="$1"

    # Check if "all" is in skip list
    if (( ${SKIP_EPOCHS[(Ie)all]} )); then
        return 0
    fi

    # Check if specific epoch is in skip list
    if (( ${SKIP_EPOCHS[(Ie)$epoch]} )); then
        return 0
    fi

    return 1
}

# Check if a URL is a valid git repository
is_valid_git_repo() {
    local url="$1"
    git ls-remote --exit-code "$url" &>/dev/null
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --skip)
                if [[ -z "$2" ]]; then
                    print_error "--skip requires an argument"
                    exit 1
                fi
                if [[ "$2" == "all" ]]; then
                    SKIP_EPOCHS=(all)
                else
                    SKIP_EPOCHS=(${(s:,:)2})
                fi
                shift 2
                ;;
            --jobs)
                if [[ -z "$2" || ! "$2" =~ ^[0-9]+$ ]]; then
                    print_error "--jobs requires a positive integer argument"
                    exit 1
                fi
                JOBS="$2"
                shift 2
                ;;
            --prefix)
                if [[ -z "$2" ]]; then
                    print_error "--prefix requires a URL argument"
                    exit 1
                fi
                LIST_PREFIX="$2"
                [[ "$LIST_PREFIX" != */ ]] && LIST_PREFIX="${LIST_PREFIX}/"
                shift 2
                ;;
            --max-epoch)
                if [[ -z "$2" || ! "$2" =~ ^[0-9]+$ ]]; then
                    print_error "--max-epoch requires a positive integer argument"
                    exit 1
                fi
                MAX_EPOCH="$2"
                shift 2
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

# Main script
main() {
    local list_name=""

    parse_args "$@"

    print_info "Cloning email list: ${BLUE}${list_name}${NC}"
    print_info "Using URL prefix: ${LIST_PREFIX}"

    # Create or enter the list directory
    if [[ -d "$list_name" ]]; then
        print_warning "Directory '$list_name' already exists"
    else
        print_info "Creating directory: $list_name"
        mkdir -p "$list_name" || {
            print_error "Failed to create directory: $list_name"
            exit 1
        }
    fi

    cd "$list_name" || {
        print_error "Failed to enter directory: $list_name"
        exit 1
    }

    # Check git repository state
    if git rev-parse --git-dir &>/dev/null; then
        local current_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
        if [[ "$current_branch" != "main" ]]; then
            print_error "Existing repository is on branch '$current_branch', not 'main'"
            print_error "This script requires the repository to be on the 'main' branch"
            exit 1
        fi
        print_warning "Using existing git repository on 'main' branch"
    else
        print_info "Initializing git repository"
        git init -b main || {
            print_error "Failed to initialize git repository"
            exit 1
        }
    fi

    # Discover valid epoch repositories
    print_info "Discovering epoch repositories..."
    local list_repo_prefix="${LIST_PREFIX}${list_name}/"
    local -a valid_epochs
    local -a valid_urls

    for (( i=0; i<=MAX_EPOCH; i++ )); do
        local list_repo="${list_repo_prefix}${i}"
        print -n "  Checking epoch $i... "

        if is_valid_git_repo "$list_repo"; then
            print "found"
            valid_epochs+=($i)
            valid_urls+=("$list_repo")
        else
            print "not found"
            break
        fi
    done

    if (( ${#valid_epochs} == 0 )); then
        print_error "No valid epoch repositories found for list: $list_name"
        exit 1
    fi

    print_success "Found ${#valid_epochs} epoch repositories:"
    for i in "${valid_epochs[@]}"; do
        local url="${list_repo_prefix}${i}"
        if should_skip_epoch "$i"; then
            print "  [$i] $url ${YELLOW}(will skip)${NC}"
        else
            print "  [$i] $url"
        fi
    done

    # Filter out skipped epochs
    local -a epochs_to_clone
    for epoch in "${valid_epochs[@]}"; do
        if ! should_skip_epoch "$epoch"; then
            epochs_to_clone+=($epoch)
        fi
    done

    if (( ${#epochs_to_clone} == 0 )); then
        print_warning "All epochs are being skipped. Nothing to do."
        exit 0
    fi

    # Confirm before proceeding
    if ! confirm "\nProceed with cloning ${#epochs_to_clone} epoch repositories?"; then
        print_info "Aborted by user"
        exit 0
    fi

    # Clone epoch repositories
    print_info "\nCloning epoch repositories..."
    local -a clones_needed
    local -a existing_remotes

    # Check which clones are already done
    for epoch in "${epochs_to_clone[@]}"; do
        local remote_name="e${epoch}"
        local clone_dir="../${list_name}.${epoch}.git"
        local upstream_url="${list_repo_prefix}${epoch}"

        # Check if remote already exists and points to upstream
        if git remote get-url "$remote_name" &>/dev/null; then
            local current_url=$(git remote get-url "$remote_name")
            if [[ "$current_url" == "$upstream_url" ]]; then
                print_info "Epoch $epoch: remote already configured with upstream URL"
                existing_remotes+=($epoch)
                continue
            fi
        fi

        # Check if clone directory exists
        if [[ -d "$clone_dir" && -d "${clone_dir}/.git" ]]; then
            print_info "Epoch $epoch: clone directory already exists"
            existing_remotes+=($epoch)
        else
            clones_needed+=($epoch)
        fi
    done

    # Perform clones
    if (( ${#clones_needed} > 0 )); then
        print_info "Need to clone ${#clones_needed} repositories"

        for epoch in "${clones_needed[@]}"; do
            local clone_url="${list_repo_prefix}${epoch}"
            local clone_dir="../${list_name}.${epoch}.git"

            print_info "\nCloning epoch $epoch from $clone_url"
            print_info "Destination: $clone_dir"

            while true; do
                if git clone "$clone_url" "$clone_dir"; then
                    print_success "Epoch $epoch cloned successfully"
                    break
                else
                    print_error "Failed to clone epoch $epoch"
                    print_warning "Clone failed. Options:"
                    print "  [r] Retry the clone"
                    print "  [s] Skip this epoch"
                    print "  [a] Abort script"
                    print -n "Choose [r/s/a]: "
                    read -r choice

                    case "$choice" in
                        r|R)
                            print_info "Retrying clone..."
                            continue
                            ;;
                        s|S)
                            print_warning "Skipping epoch $epoch"
                            break
                            ;;
                        a|A)
                            print_info "Aborting script"
                            exit 1
                            ;;
                        *)
                            print_error "Invalid choice"
                            ;;
                    esac
                fi
            done
        done
    else
        print_info "All needed clones already exist"
    fi

    # Add remotes pointing to local clones
    print_info "\nConfiguring remotes in local repository..."
    for epoch in "${epochs_to_clone[@]}"; do
        local remote_name="e${epoch}"
        local clone_dir="../${list_name}.${epoch}.git"

        if ! [[ -d "$clone_dir" ]]; then
            print_warning "Clone directory missing for epoch $epoch, skipping remote setup"
            continue
        fi

        if git remote get-url "$remote_name" &>/dev/null; then
            local current_url=$(git remote get-url "$remote_name")
            print_info "Remote '$remote_name' already exists: $current_url"
        else
            print_info "Adding remote '$remote_name' -> $clone_dir"
            git remote add "$remote_name" "$clone_dir" || {
                print_error "Failed to add remote '$remote_name'"
                exit 1
            }
        fi
    done

    # Fetch from all remotes
    print_info "\nFetching from all remotes (using $JOBS parallel jobs)..."
    if git fetch --all --jobs="$JOBS"; then
        print_success "Fetch completed successfully"
    else
        print_error "Fetch failed"
        exit 1
    fi

    # Repoint remotes to upstream URLs
    print_info "\nRepointing remotes to upstream URLs..."
    local -a remotes_to_update

    for epoch in "${epochs_to_clone[@]}"; do
        local remote_name="e${epoch}"
        local upstream_url="${list_repo_prefix}${epoch}"

        if ! git remote get-url "$remote_name" &>/dev/null; then
            print_warning "Remote '$remote_name' does not exist, skipping"
            continue
        fi

        local current_url=$(git remote get-url "$remote_name")

        if [[ "$current_url" == "$upstream_url" ]]; then
            print_info "Remote '$remote_name' already points to upstream"
        else
            print_info "Updating remote '$remote_name' to $upstream_url"
            git remote set-url "$remote_name" "$upstream_url" || {
                print_error "Failed to update remote '$remote_name'"
                exit 1
            }
            remotes_to_update+=($remote_name)
        fi
    done

    # Verify upstream remotes work
    if (( ${#remotes_to_update} > 0 )); then
        print_info "\nVerifying upstream remotes..."
        if git fetch --all --jobs="$JOBS" --dry-run; then
            print_success "All upstream remotes verified"
        else
            print_error "Failed to verify upstream remotes"
            exit 1
        fi
    fi

    # Clean up local clones
    print_info "\nCleaning up local clone directories..."
    if confirm "Delete local clone directories?"; then
        for epoch in "${epochs_to_clone[@]}"; do
            local clone_dir="../${list_name}.${epoch}.git"
            if [[ -d "$clone_dir" ]]; then
                print_info "Removing $clone_dir"
                rm -rf "$clone_dir" || {
                    print_warning "Failed to remove $clone_dir"
                }
            fi
        done
        print_success "Cleanup completed"
    else
        print_info "Keeping local clone directories"
    fi

    print_success "\n✓ Email list '$list_name' successfully cloned and configured!"
    print_info "Repository location: $(pwd)"
    print_info "Total remotes configured: ${#epochs_to_clone}"
}

# Run main function with all arguments
main "$@"
