# Configuration System Walkthrough

## Example Scenario: Handling Problematic Epochs

Let's walk through a realistic scenario where some epochs have issues.

### Initial Setup

You want to clone the `lkml` mailing list, but you've discovered:
- Epoch 5 has intermittent server problems
- Epoch 12 has been moved to a mirror
- You want to keep local backups of all clones for now

### Step 1: Initial Clone with Configuration

```bash
./clone-list.zsh \
  --set-local 5 \
  --set-mirror 12=https://backup.lore.kernel.org/lkml/12 \
  --keep-clones \
  lkml
```

**What happens:**
```
INFO: Cloning email list: lkml
INFO: Using URL prefix: https://lore.kernel.org/

INFO: Applying local-only configuration...
SUCCESS: Epoch 5 marked as local-only

INFO: Applying mirror configuration...
SUCCESS: Epoch 12 configured with mirror: https://backup.lore.kernel.org/lkml/12

⚙  Special configuration detected:
  Epoch 5: local-only (will keep clone)
  Epoch 12: mirror -> https://backup.lore.kernel.org/lkml/12
  (Use --show-config to see full configuration)

⚙  --keep-clones: All local clones will be preserved

INFO: Discovering epoch repositories...
  Checking epoch 0... found
  Checking epoch 1... found
  ...
  Checking epoch 17... found
  Checking epoch 18... not found

SUCCESS: Found 18 epoch repositories:
  [0] https://lore.kernel.org/lkml/0
  [1] https://lore.kernel.org/lkml/1
  ...
  [5] https://lore.kernel.org/lkml/5 (special: local-only)
  ...
  [12] https://lore.kernel.org/lkml/12 (special: mirror)
  ...
  [17] https://lore.kernel.org/lkml/17

Proceed with cloning 18 epoch repositories? [y/N] y

INFO: Cloning epoch repositories...
[... cloning happens ...]

INFO: Repointing remotes to upstream URLs...
INFO: Remote 'e0' updated to https://lore.kernel.org/lkml/0
...
INFO: Remote 'e5' kept as local-only: ../lkml.5.git
...
INFO: Remote 'e12' updated to mirror: https://backup.lore.kernel.org/lkml/12
...

INFO: Cleaning up local clone directories...
Keeping 18 local clone(s) based on configuration:
  - Epoch 0 (--keep-clones flag)
  - Epoch 1 (--keep-clones flag)
  ...
  - Epoch 5 (local-only mode)
  ...
  - Epoch 12 (--keep-clones flag)
  ...

SUCCESS: ✓ Email list 'lkml' successfully cloned and configured!
```

### Step 2: View Configuration

```bash
./clone-list.zsh --show-config lkml
```

**Output:**
```
Configuration for list: lkml

Epoch 5 (e5):
  Mode: local-only (keeps local clone, no upstream URL)

Epoch 12 (e12):
  Mode: mirror (uses alternative URL)
  Mirror URL: https://backup.lore.kernel.org/lkml/12

Configuration is stored in git config (remote.eN.clone-list-*)
Use --set-local or --set-mirror to configure epochs
```

### Step 3: Graft the Epochs

```bash
./graft-list.zsh lkml
```

**What happens:**
```
==> Grafting email list epochs: lkml

INFO: Repository: /path/to/lkml

==> Discovering epoch remotes...
SUCCESS: Found 18 epoch remotes: e0 through e17

⚠ WARNING: ⚙  Special epoch configuration detected:
  Local-only epochs: 5
    These epochs use local clones and may not be up-to-date with upstream
  Mirror epochs: 12
    e12: https://backup.lore.kernel.org/lkml/12

This will create a 'combined' branch by grafting 18 epochs together.
WARNING: This operation rewrites git history and may take several minutes.
Proceed with grafting? [y/N] y

[... grafting happens ...]

SUCCESS: ✓ Grafting complete!
INFO: Repository: /path/to/lkml
INFO: Branch: combined
INFO: Total commits: 4567890
INFO: Epochs grafted: e0 through e17 (18 total)
```

### Step 4: Later - Update Configuration

A few days later, epoch 5 server is fixed. Remove the local-only configuration:

```bash
cd lkml
git config --unset remote.e5.clone-list-mode
git remote set-url e5 https://lore.kernel.org/lkml/5
rm -rf ../lkml.5.git  # Clean up old local clone

# Fetch from the now-working upstream
git fetch e5
```

### Step 5: Add a New Epoch

Later, a new epoch 18 is created upstream. Re-run clone-list:

```bash
./clone-list.zsh lkml
```

**What happens:**
```
INFO: Using existing git repository on 'main' branch

⚙  Special configuration detected:
  Epoch 12: mirror -> https://backup.lore.kernel.org/lkml/12
  (Use --show-config to see full configuration)

INFO: Discovering epoch repositories...
  ...
  Checking epoch 17... found
  Checking epoch 18... found
  Checking epoch 19... not found

SUCCESS: Found 19 epoch repositories:
  [0] https://lore.kernel.org/lkml/0
  ...
  [18] https://lore.kernel.org/lkml/18 (NEW)

INFO: Epoch 0: remote already configured with upstream URL
...
INFO: Epoch 17: remote already configured with upstream URL

Need to clone 1 repositories

INFO: Cloning epoch 18...
[... only epoch 18 gets cloned ...]

SUCCESS: ✓ Email list 'lkml' successfully cloned and configured!
```

Then re-graft:

```bash
./graft-list.zsh --overwrite lkml
```

## Configuration Persistence Example

### Inspect Configuration Directly

```bash
cd lkml

# View all clone-list configuration
git config --get-regexp 'remote\.e.*\.clone-list'
```

**Output:**
```
remote.e12.clone-list-mode mirror
remote.e12.clone-list-mirror-url https://backup.lore.kernel.org/lkml/12
```

### Share Configuration with Team

Since git config is local, create a setup script:

```bash
cat > setup-lkml-config.sh << 'EOF'
#!/bin/bash
# Apply known problematic epoch configurations for lkml

cd lkml || exit 1

echo "Applying LKML epoch configuration..."

# Epoch 12 uses a mirror
git config remote.e12.clone-list-mode mirror
git config remote.e12.clone-list-mirror-url https://backup.lore.kernel.org/lkml/12

echo "Configuration applied. Run ./clone-list.zsh lkml to sync."
EOF

chmod +x setup-lkml-config.sh
```

Team members can run:
```bash
./setup-lkml-config.sh
./clone-list.zsh lkml
```

## Visual Representation

### Remote URL Progression

**Standard Epoch (e0):**
```
Initial:        (none)
After clone:    ../lkml.0.git (local)
After repoint:  https://lore.kernel.org/lkml/0 (upstream)
After cleanup:  https://lore.kernel.org/lkml/0 (upstream)
                ../lkml.0.git DELETED
```

**Local-Only Epoch (e5):**
```
Initial:        (none)
After clone:    ../lkml.5.git (local)
After repoint:  ../lkml.5.git (local) ⚠️ stays local
After cleanup:  ../lkml.5.git (local) ⚠️ stays local
                ../lkml.5.git KEPT
```

**Mirror Epoch (e12):**
```
Initial:        (none)
After clone:    ../lkml.12.git (local)
After repoint:  https://backup.lore.kernel.org/lkml/12 (mirror)
After cleanup:  https://backup.lore.kernel.org/lkml/12 (mirror)
                ../lkml.12.git DELETED (unless --keep-clones)
```

## Benefits Demonstrated

1. **No manual memory required**: Configuration is stored in the repo
2. **Clear feedback**: Scripts show configuration during execution
3. **Flexible recovery**: Easy to adjust as situations change
4. **Team coordination**: Can share configuration via scripts
5. **Idempotent**: Safe to re-run with configuration in place
6. **Per-epoch control**: Fine-grained management

## Common Commands Quick Reference

```bash
# Set up problematic epochs
./clone-list.zsh --set-local 5 --set-mirror 12=https://mirror.com/lkml/12 lkml

# View configuration
./clone-list.zsh --show-config lkml

# Or inspect directly
cd lkml && git config --get-regexp 'remote\.e.*\.clone-list'

# Update configuration
cd lkml
git config remote.e5.clone-list-mode mirror
git config remote.e5.clone-list-mirror-url https://mirror.com/lkml/5

# Remove configuration
git config --unset remote.e5.clone-list-mode
git config --unset remote.e5.clone-list-mirror-url

# Re-clone after config changes
cd .. && ./clone-list.zsh lkml

# Graft with configuration awareness
./graft-list.zsh lkml
```
