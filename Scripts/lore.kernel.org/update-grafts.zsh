#!/usr/bin/env zsh
#
# fetch-and-graft.zsh - Fetch and graft git repositories in parallel
#
# DESCRIPTION:
#   For each immediate subdirectory (depth 1) that contains a git repository,
#   this script runs `git fetch --all` and then `graft-list.zsh` to update
#   and stitch together the repository history. Supports parallel execution
#   for faster processing of multiple repositories.
#
# USAGE:
#   fetch-and-graft.zsh [OPTIONS]
#
# OPTIONS:
#   --jobs N, -j N       Number of parallel jobs (default: 1)
#   -h, --help           Show this help message
#
# EXAMPLES:
#   fetch-and-graft.zsh
#   fetch-and-graft.zsh --jobs 4
#   fetch-and-graft.zsh -j 8
#
# NOTES:
#   - Directories matching *.git are skipped
#   - When jobs > 1, fetch and graft output is silenced
#   - If graft-list.zsh fails for any repo, the script exits non-zero
#   - Respects NO_COLOR environment variable for output
#   - Press Ctrl-C to gracefully terminate all running jobs
#

emulate -L zsh
setopt nullglob extended_glob pipefail

# Array indexes should start at 0, not 1
setopt ksh_arrays

# Load datetime module for timestamps
zmodload zsh/datetime

# Get the script path for help text
readonly SCRIPT_PATH="${0:A}"

# Color codes for output
# Respect NO_COLOR environment variable: https://no-color.org/
if [[ -n "${NO_COLOR:-}" ]] || [[ ! -t 1 ]]; then
    readonly RED=''
    readonly YELLOW=''
    readonly GREEN=''
    readonly CYAN=''
    readonly NC=''
    readonly BOLD_RED=''
    readonly BOLD_YELLOW=''
    readonly BOLD_CYAN=''
else
    readonly RED='\033[0;31m'
    readonly YELLOW='\033[1;33m'
    readonly GREEN='\033[0;32m'
    readonly CYAN='\033[0;36m'
    readonly NC='\033[0m' # No Color
    readonly BOLD_RED='\033[1;31m'
    readonly BOLD_YELLOW='\033[1;33m'
    readonly BOLD_CYAN='\033[1;36m'
fi

# Print functions
print_error() {
    printf "${BOLD_RED}ERROR:${NC} %s\n" "$*" >&2
}

print_warning() {
    printf "${BOLD_YELLOW}WARNING:${NC} %s\n" "$*" >&2
}

print_info() {
    printf "${BOLD_CYAN}INFO:${NC} %s\n" "$*"
}

print_success() {
    printf "${GREEN}SUCCESS:${NC} %s\n" "$*"
}

# For printing formatted strings that may contain color codes
print_fmt() {
    printf "%b\n" "$*"
}

# Get current timestamp in HH:MM:SS format
get_timestamp() {
    strftime "%H:%M:%S" $EPOCHSECONDS
}

# Show usage information
show_usage() {
    sed -n '/^# DESCRIPTION:/,/^$/p' "$SCRIPT_PATH" | sed 's/^# \?//'
}

# Global flag for signal handling
typeset -i SHUTTING_DOWN=0
typeset -a ACTIVE_PIDS=()

# Signal handler for cleanup
cleanup_handler() {
    if (( SHUTTING_DOWN )); then
        return
    fi
    SHUTTING_DOWN=1

    print_warning "Received interrupt signal, shutting down gracefully..."

    # Try graceful termination first (SIGTERM)
    if (( ${#ACTIVE_PIDS[@]} > 0 )); then
        print_info "Sending TERM signal to ${#ACTIVE_PIDS[@]} running jobs..."
        for pid in ${ACTIVE_PIDS[@]}; do
            kill -TERM $pid 2>/dev/null
        done

        # Wait up to 5 seconds for graceful shutdown
        typeset -i wait_time=0
        while (( wait_time < 50 )); do
            typeset -a still_running=()
            for pid in ${ACTIVE_PIDS[@]}; do
                if kill -0 $pid 2>/dev/null; then
                    still_running+=($pid)
                fi
            done

            if (( ${#still_running[@]} == 0 )); then
                break
            fi

            ACTIVE_PIDS=("${still_running[@]}")
            sleep 0.1
            (( wait_time++ ))
        done

        # Force kill any remaining jobs
        if (( ${#ACTIVE_PIDS[@]} > 0 )); then
            print_warning "Force killing ${#ACTIVE_PIDS[@]} remaining jobs..."
            for pid in ${ACTIVE_PIDS[@]}; do
                kill -KILL $pid 2>/dev/null
            done
            # Give them a moment to die
            sleep 0.2
        fi
    fi

    print_info "Cleanup complete"
    exit 130
}

# Set up signal traps
trap cleanup_handler INT TERM

# Parse command-line arguments using zparseopts
typeset -A opts
zparseopts -D -E -A opts -- j: -jobs: h -help

if [[ -n ${opts[(i)-h]} ]] || [[ -n ${opts[(i)--help]} ]]; then
    show_usage
    exit 0
fi

# Get jobs value
typeset -i JOBS=1
if [[ -n ${opts[(i)-j]} ]]; then
    JOBS=${opts[-j]}
elif [[ -n ${opts[(i)--jobs]} ]]; then
    JOBS=${opts[--jobs]}
fi

# Validate jobs value
if [[ ! "$JOBS" =~ ^[0-9]+$ ]] || (( JOBS < 1 )); then
    print_error "--jobs must be a positive integer"
    exit 1
fi

# Check for unexpected arguments
if [[ $# -gt 0 ]]; then
    print_error "Unknown arguments: $*"
    show_usage
    exit 1
fi

# Function to format elapsed time
format_time() {
    local -F seconds=$1
    if (( seconds < 60 )); then
        printf "%.1fs" $seconds
    else
        typeset -i minutes=$((seconds / 60))
        typeset -i secs=$((seconds % 60))
        printf "%dm %ds" $minutes $secs
    fi
}

# Function to process a single repository
process_repo() {
    local dir=$1
    local name=${dir:t}
    local silent=$2
    local -F start_time=$EPOCHSECONDS

    # Validate that we have a proper name (should never happen with proper collection)
    if [[ -z $name ]]; then
        print_error "Invalid directory path (empty name): '$dir'"
        return 1
    fi

    if [[ $silent == "true" ]]; then
        # Silent mode for parallel execution - print structured messages
        local timestamp=$(get_timestamp)
        print_fmt "${CYAN}[$timestamp]${NC} ${CYAN}[$name]${NC} started"

        if (cd -- "$dir" && git fetch --all &>/dev/null); then
            : # fetch succeeded
        else
            local -F elapsed=$((EPOCHSECONDS - start_time))
            timestamp=$(get_timestamp)
            print_fmt "${CYAN}[$timestamp]${NC} ${RED}[$name]${NC} fetch failed after $(format_time $elapsed) — skipping graft-list"
            return 1
        fi

        if graft-list.zsh --overwrite --yes "$name" &>/dev/null; then
            local -F elapsed=$((EPOCHSECONDS - start_time))
            timestamp=$(get_timestamp)
            print_fmt "${CYAN}[$timestamp]${NC} ${GREEN}[$name]${NC} completed in $(format_time $elapsed)"
        else
            local -F elapsed=$((EPOCHSECONDS - start_time))
            timestamp=$(get_timestamp)
            print_fmt "${CYAN}[$timestamp]${NC} ${RED}[$name]${NC} graft-list.zsh failed after $(format_time $elapsed)"
            return 1
        fi
    else
        # Verbose mode for single job
        local timestamp=$(get_timestamp)
        print_fmt "${CYAN}[$timestamp]${NC} ${CYAN}[$name]${NC} fetching…"
        if (cd -- "$dir" && git fetch --all); then
            timestamp=$(get_timestamp)
            print_fmt "${CYAN}[$timestamp]${NC} ${GREEN}[$name]${NC} fetch ok"
        else
            local -F elapsed=$((EPOCHSECONDS - start_time))
            timestamp=$(get_timestamp)
            print_fmt "${CYAN}[$timestamp]${NC} ${RED}[$name]${NC} fetch failed after $(format_time $elapsed) — skipping graft-list"
            return 1
        fi

        if ! graft-list.zsh --overwrite --yes "$name"; then
            local -F elapsed=$((EPOCHSECONDS - start_time))
            timestamp=$(get_timestamp)
            print_fmt "${CYAN}[$timestamp]${NC} ${RED}[$name]${NC} graft-list.zsh failed after $(format_time $elapsed) — aborting"
            return 1
        fi

        local -F elapsed=$((EPOCHSECONDS - start_time))
        timestamp=$(get_timestamp)
        print_fmt "${CYAN}[$timestamp]${NC} ${GREEN}[$name]${NC} completed in $(format_time $elapsed)"
    fi

    return 0
}

# Collect all valid repositories
typeset -a repos
for dir in ./*(/N); do
    # Ensure dir is not empty
    [[ -z $dir ]] && continue

    # Get basename
    name=${dir:t}

    # Skip if name is empty or invalid
    if [[ -z $name ]]; then
        print_warning "Skipping directory with empty name: '$dir'"
        continue
    fi

    # Skip *.git directories
    [[ $name == *.git ]] && continue

    # Check if it's a git repository
    if [[ -d $dir/.git || -f $dir/.git ]]; then
        repos+=("$dir")
    else
        print_fmt "${YELLOW}[$name]${NC} skipped (not a git repo)"
    fi
done

if (( ${#repos[@]} == 0 )); then
    print_info "No git repositories found"
    exit 0
fi

# Process repositories
typeset -i failed=0
typeset -i completed=0
typeset -i total=${#repos[@]}

if (( JOBS == 1 )); then
    # Sequential processing with verbose output
    print_info "Processing $total repositories sequentially"
    for dir in "${repos[@]}"; do
        if (( SHUTTING_DOWN )); then
            break
        fi

        (( completed++ ))

        if ! process_repo "$dir" "false"; then
            name=${dir:t}
            print_error "[$name] Processing failed — aborting"
            exit 1
        fi
    done

    print_success "All $total repositories processed successfully"
else
    # Parallel processing with silent output
    print_info "Processing $total repositories with $JOBS parallel jobs"

    # Track jobs: PID -> repo dir mapping
    typeset -A pid_to_dir
    typeset -i repo_idx=0

    # Main processing loop
    while (( repo_idx < total )) || (( ${#ACTIVE_PIDS[@]} > 0 )); do
        if (( SHUTTING_DOWN )); then
            break
        fi

        # Start new jobs up to the limit
        while (( ${#ACTIVE_PIDS[@]} < JOBS )) && (( repo_idx < total )); do
            local dir="${repos[$repo_idx]}"
            (( repo_idx++ ))

            # Extra safety check before spawning
            if [[ -z "${dir}" ]]; then
                print_error "Encountered empty directory path at index $(( repo_idx - 1 ))"
                (( failed++ ))
                continue
            fi

            process_repo "$dir" "true" &
            local pid=$!
            ACTIVE_PIDS+=($pid)
            pid_to_dir[$pid]="$dir"
        done

        # Wait for at least one job to complete
        if (( ${#ACTIVE_PIDS[@]} > 0 )); then
            # Check each active PID
            typeset -a new_active=()
            typeset -i any_completed=0

            for pid in ${ACTIVE_PIDS[@]}; do
                if kill -0 $pid 2>/dev/null; then
                    # Still running
                    new_active+=($pid)
                else
                    # Job completed - reap it
                    wait $pid 2>/dev/null
                    local exit_status=$?
                    if (( exit_status != 0 )); then
                        (( failed++ ))
                    fi
                    (( completed++ ))
                    (( any_completed++ ))
                    unset "pid_to_dir[$pid]"
                fi
            done

            ACTIVE_PIDS=("${new_active[@]}")

            # If no jobs completed this cycle and we still have active jobs,
            # sleep briefly before checking again
            if (( any_completed == 0 )) && (( ${#ACTIVE_PIDS[@]} > 0 )); then
                sleep 0.1
            fi
        fi
    done

    if (( SHUTTING_DOWN )); then
        print_error "Processing interrupted by user"
        exit 130
    fi

    if (( failed > 0 )); then
        print_error "$failed of $total repositories failed processing"
        exit 1
    else
        print_success "All $total repositories processed successfully"
    fi
fi

exit 0
