# Email List Cloning and Grafting Scripts

## Overview

Two complementary zsh scripts for working with email list archives from lore.kernel.org:

1. **clone-list.zsh** - Discovers, clones, and configures epoch repositories
2. **graft-list.zsh** - Stitches epochs into a single linear git history

## Configuration System

The scripts use **git config** to store persistent per-epoch configuration. This is ideal for handling problematic epochs that require special treatment.

### Configuration Storage

Configuration is stored in git config under `remote.eN.clone-list-*`:

```bash
# Mark epoch as local-only (keeps local clone, doesn't point to upstream)
git config remote.e5.clone-list-mode local

# Mark epoch to use a mirror URL
git config remote.e5.clone-list-mode mirror
git config remote.e5.clone-list-mirror-url https://mirror.example.com/list/5
```

### Why Git Config?

- **Git-native**: Uses built-in git functionality
- **Per-repository**: Configuration stays with the repo
- **Persistent**: Survives across script runs
- **Non-intrusive**: Doesn't pollute the working directory
- **Easy to inspect**: `git config --get-regexp remote.e`

## Usage Examples

### Basic Workflow

```bash
# Clone all epochs for a list
./clone-list.zsh lkml

# Graft epochs into a single history
./graft-list.zsh lkml

# Explore the combined history
cd lkml
git log combined
git log --grep='memory leak' combined
```

### Handling Problematic Epochs

#### Scenario 1: Server temporarily unavailable

```bash
# Clone the list, marking epoch 5 as local-only
./clone-list.zsh --set-local 5 lkml

# This will:
# - Clone epoch 5 like normal
# - Keep the local clone (not delete it)
# - Not update the remote URL to upstream
# - The remote will continue pointing to ../lkml.5.git
```

#### Scenario 2: Using a mirror for a problematic epoch

```bash
# Configure epoch 5 to use a mirror
./clone-list.zsh --set-mirror 5=https://backup.example.com/lkml/5 lkml

# This will:
# - Clone from the mirror URL
# - Point the remote to the mirror (not upstream)
# - Allow normal operation with alternative source
```

#### Scenario 3: Keep all local clones

```bash
# Keep all local clones (for backup or offline work)
./clone-list.zsh --keep-clones lkml

# This keeps ALL epoch clones in ../lkml.N.git directories
# Useful for:
# - Creating backups
# - Offline work
# - Avoiding re-cloning if something goes wrong
```

### Configuration Management

#### View current configuration

```bash
./clone-list.zsh --show-config lkml
```

Output example:
```
Configuration for list: lkml

Epoch 5 (e5):
  Mode: local-only (keeps local clone, no upstream URL)

Epoch 7 (e7):
  Mode: mirror (uses alternative URL)
  Mirror URL: https://backup.example.com/lkml/7

Configuration is stored in git config (remote.eN.clone-list-*)
Use --set-local or --set-mirror to configure epochs
```

#### Multiple problematic epochs

```bash
# Mark multiple epochs as local-only
./clone-list.zsh --set-local 3,5,7 lkml

# Combine different configurations
./clone-list.zsh \
  --set-local 3 \
  --set-mirror 5=https://mirror.com/lkml/5 \
  lkml
```

#### Manual configuration

You can also set configuration manually:

```bash
cd lkml
git config remote.e5.clone-list-mode local
git config remote.e7.clone-list-mode mirror
git config remote.e7.clone-list-mirror-url https://mirror.example.com/lkml/7
```

### Re-running Scripts

The scripts are idempotent and configuration-aware:

```bash
# Initial clone
./clone-list.zsh lkml

# Later, discover a new epoch exists
./clone-list.zsh lkml  # Only clones new epochs

# Or update configuration
./clone-list.zsh --set-local 17 lkml  # Adds new config, re-runs

# Re-graft after new epochs
./graft-list.zsh --overwrite lkml  # Rebuilds combined branch
```

## Configuration Impact on Scripts

### clone-list.zsh behavior

For each epoch, the script checks configuration:

1. **No configuration** (default):
   - Clones to temp location
   - Creates remote pointing to local clone
   - Fetches data
   - Updates remote URL to upstream
   - Deletes local clone

2. **Mode: local**:
   - Clones to temp location
   - Creates remote pointing to local clone
   - Fetches data
   - **Keeps remote pointing to local clone** ⚠️
   - **Keeps local clone** ⚠️

3. **Mode: mirror**:
   - Clones from mirror URL
   - Creates remote pointing to local clone
   - Fetches data
   - **Updates remote URL to mirror** ⚠️
   - Deletes local clone (unless --keep-clones)

### graft-list.zsh behavior

The graft script is aware of configuration and displays warnings:

```
⚙  Special epoch configuration detected:
  Local-only epochs: 5 7
    These epochs use local clones and may not be up-to-date with upstream
```

This reminds you that local-only epochs might be stale.

## Flags Reference

### clone-list.zsh

```
--skip <epochs>           Skip processing these epochs entirely (e.g., --skip 5,7)
--keep-clones             Keep ALL local clones (don't delete any)
--set-local <epochs>      Mark epochs as local-only (e.g., --set-local 3,5)
--set-mirror <e>=<url>    Configure mirror URL (e.g., --set-mirror 5=https://...)
--show-config             Display current configuration and exit
--jobs <n>                Parallel fetch jobs (default: 8)
--prefix <url>            URL prefix override
--max-epoch <n>           Maximum epoch to check (default: 32)
```

### graft-list.zsh

```
--overwrite               Overwrite existing 'combined' branch
--dry-run                 Show what would happen without making changes
```

## Typical Workflows

### Workflow 1: First-time clone

```bash
./clone-list.zsh lkml
./graft-list.zsh lkml
```

### Workflow 2: Update with new epochs

```bash
cd lkml
git fetch --all  # Check for new epochs

# If new epoch exists
cd ..
./clone-list.zsh lkml  # Auto-detects and clones new epochs
./graft-list.zsh --overwrite lkml  # Rebuilds combined branch
```

### Workflow 3: Recover from server outage

```bash
# Server for epoch 5 is down
./clone-list.zsh --set-local 5 lkml

# Work continues with local copy
# Later when server is back up:
cd lkml
git config --unset remote.e5.clone-list-mode
git remote set-url e5 https://lore.kernel.org/lkml/5
git fetch e5
rm -rf ../lkml.5.git  # Clean up local clone
```

### Workflow 4: Permanent mirror setup

```bash
# Epoch 5 permanently moved to mirror
./clone-list.zsh --set-mirror 5=https://mirror.example.com/lkml/5 lkml

# Configuration persists, no need to remember
# Future runs automatically use mirror
```

## Benefits of This Approach

1. **No manual tracking**: Configuration stored in repo
2. **Visible**: Scripts display configuration during runs
3. **Flexible**: Per-epoch control
4. **Persistent**: Survives script re-runs
5. **Inspectable**: `git config --get-regexp remote.e`
6. **Standard**: Uses git's built-in config system
7. **Non-intrusive**: No files in working directory

## Advanced: Direct Config Inspection

```bash
cd lkml

# See all clone-list configuration
git config --get-regexp 'remote\.e[0-9]+\.clone-list'

# Check specific epoch
git config --get remote.e5.clone-list-mode
git config --get remote.e5.clone-list-mirror-url

# Remove configuration
git config --unset remote.e5.clone-list-mode
git config --unset remote.e5.clone-list-mirror-url
```

## Troubleshooting

**Q: Script says "epoch already configured" but I want to re-clone**

```bash
cd lkml
git config --unset remote.e5.clone-list-mode
git remote set-url e5 https://lore.kernel.org/lkml/5
rm -rf ../lkml.5.git
cd ..
./clone-list.zsh lkml
```

**Q: How do I reset everything?**

```bash
cd lkml
# Remove all clone-list config
git config --get-regexp 'remote\.e[0-9]+\.clone-list' | cut -d' ' -f1 | xargs -n1 git config --unset
```

**Q: Can I commit configuration?**

The git config is stored in `.git/config` which is not committed. If you want to share configuration, create a script:

```bash
#!/bin/bash
# setup-lkml-config.sh
git config remote.e5.clone-list-mode local
git config remote.e7.clone-list-mode mirror
git config remote.e7.clone-list-mirror-url https://mirror.example.com/lkml/7
```
