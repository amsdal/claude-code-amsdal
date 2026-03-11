---
name: amsdal-workspace
description: Setup or update AMSDAL source workspace — clone/pull all repos as git submodules
user-invocable: true
---

# AMSDAL Workspace Setup

This command sets up or updates the AMSDAL source code workspace with all repositories as git submodules.

## Instructions for Claude

When the user invokes this command, follow these steps exactly:

### Step 1: Determine workspace path

Check if `AMSDAL_WORKSPACE` environment variable is set:
```bash
echo "$AMSDAL_WORKSPACE"
```

If not set or empty, ask the user where they want the workspace. Suggest `~/amsdal_workspace` as default.

### Step 2: Ask git host preference

Ask the user which git host to use for SSH cloning. Options:
- `github.com` (default) — standard GitHub SSH: `git@github.com:amsdal/...`
- Custom alias — e.g. `github-alias` for `git@github-alias:amsdal/...`

### Step 3: Verify SSH connectivity

Before any git operations, test SSH access:
```bash
ssh -o BatchMode=yes -o ConnectTimeout=5 -T git@{HOST} 2>&1
```

**If it fails with "Permission denied" or "Host key verification failed":**
- Tell the user their SSH key is not loaded or not configured
- Suggest: `ssh-add ~/.ssh/id_rsa` (or their key path) to load the key into SSH agent
- Suggest: `ssh-add -l` to check loaded keys
- Do NOT proceed until SSH works

**If it fails with timeout:** suggest checking network/VPN.

**If it succeeds** (GitHub returns "Hi username!" or "successfully authenticated"): proceed.

### Step 4: Setup or update workspace

Check if the workspace directory exists and has a `.git` directory.

#### Case A: Fresh setup (directory doesn't exist or is empty)

```bash
mkdir -p {WORKSPACE_PATH}
cd {WORKSPACE_PATH}
git init
```

Then add each repository as a submodule:

```bash
git submodule add git@{HOST}:amsdal/amsdal_utils.git
git submodule add git@{HOST}:amsdal/amsdal_framework.git
git submodule add git@{HOST}:amsdal/amsdal_models.git
git submodule add git@{HOST}:amsdal/amsdal_data.git
git submodule add git@{HOST}:amsdal/amsdal_server.git
git submodule add git@{HOST}:amsdal/amsdal-glue.git
git submodule add git@{HOST}:amsdal/amsdal_cli.git
git submodule add git@{HOST}:amsdal/amsdal_ml.git
git submodule add git@{HOST}:amsdal/amsdal_mail.git
git submodule add git@{HOST}:amsdal/amsdal_storages.git
git submodule add git@{HOST}:amsdal/amsdal_langgraph.git
git submodule add git@{HOST}:amsdal/amsdal_integrations.git
git submodule add git@{HOST}:amsdal/amsdal_crm.git
```

Then initialize and clone all:
```bash
git submodule update --init --recursive
git commit -m "Add AMSDAL submodules"
```

#### Case B: Workspace exists with submodules

Pull latest changes for all submodules:
```bash
cd {WORKSPACE_PATH}
git submodule update --init --recursive
git submodule foreach 'git checkout main 2>/dev/null || git checkout master 2>/dev/null; git pull'
```

#### Case C: Workspace exists but is NOT a git repo (just cloned repos in a folder)

Ask the user if they want to:
1. Convert to submodule structure (recommended)
2. Just do `git pull` in each directory

If converting: back up, reinit as submodule repo. If just pulling:
```bash
cd {WORKSPACE_PATH}
for dir in */; do
    if [ -d "$dir/.git" ]; then
        echo "Pulling $dir..."
        (cd "$dir" && git checkout main 2>/dev/null || git checkout master 2>/dev/null; git pull)
    fi
done
```

### Step 5: Verify

List all submodules and their status:
```bash
cd {WORKSPACE_PATH}
git submodule status
```

Or if not using submodules, list directories:
```bash
ls -d */
```

### Step 6: Persist AMSDAL_WORKSPACE

If the `AMSDAL_WORKSPACE` env var is not already set permanently, add it to the user's shell profile so it survives restarts.

**Detect the user's shell and profile file:**
```bash
echo $SHELL
```

Then check if `AMSDAL_WORKSPACE` is already in the profile:
```bash
grep -q 'AMSDAL_WORKSPACE' {PROFILE_FILE} 2>/dev/null && echo "already set" || echo "not set"
```

**If not set, append it to the correct profile file:**

| Shell | OS | Profile file |
|-------|-----|-------------|
| zsh | macOS, Linux | `~/.zshrc` |
| bash | macOS | `~/.bash_profile` |
| bash | Linux (Ubuntu, Debian, Fedora, Arch, WSL) | `~/.bashrc` |
| fish | any | use `set -Ux` (no file edit needed) |

**Detect the correct profile file for bash:**
```bash
if [[ "$(uname)" == "Darwin" ]]; then
    PROFILE="$HOME/.bash_profile"
else
    PROFILE="$HOME/.bashrc"
fi
```

For zsh/bash:
```bash
echo '' >> {PROFILE_FILE}
echo '# AMSDAL workspace path' >> {PROFILE_FILE}
echo 'export AMSDAL_WORKSPACE={WORKSPACE_PATH}' >> {PROFILE_FILE}
```

For fish:
```bash
fish -c 'set -Ux AMSDAL_WORKSPACE {WORKSPACE_PATH}'
```

Also export it in the current session so it works immediately:
```bash
export AMSDAL_WORKSPACE={WORKSPACE_PATH}
```

Tell the user that `AMSDAL_WORKSPACE` has been saved and will persist after restart.

## Repository List

All repositories under the `amsdal` GitHub organization:

| Repository | Description |
|------------|-------------|
| `amsdal_utils` | Shared utilities, events system |
| `amsdal_framework` | Core framework, models, configs |
| `amsdal_models` | ORM, QuerySets, managers, migrations |
| `amsdal_data` | Data layer, connections, transactions |
| `amsdal_server` | FastAPI REST API server |
| `amsdal-glue` | ETL, CQRS, multi-source queries |
| `amsdal_cli` | CLI tool |
| `amsdal_ml` | ML plugin: embeddings, agents, MCP |
| `amsdal_mail` | Email plugin (SMTP, SES) |
| `amsdal_storages` | S3 storage plugin |
| `amsdal_langgraph` | LangGraph persistence |
| `amsdal_integrations` | Third-party integrations |
| `amsdal_crm` | CRM plugin |

## Troubleshooting

### SSH key requires passphrase
Claude Code cannot enter passphrases interactively. Load your key first:
```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/your_key
```

### Using SSH config aliases
If you use `~/.ssh/config` with host aliases:
```
Host github-work
    HostName github.com
    User git
    IdentityFile ~/.ssh/work_key
```
Specify `github-work` as the git host when prompted.

### Permission denied on some repos
Some repos may be private and require specific access. The command will skip repos that fail and report which ones were skipped.