# Git Package Manager (gitpm)

A package manager for installing and managing applications from git repositories. GitPM allows you to maintain a list of git repositories and easily install, update, and remove them with automatic dependency management and script execution.

## Features

- **Config-based repository management**: Maintain lists of git repositories in config files
- **Multiple config files**: Support for multiple config files (user and system-wide)
- **Branch support**: Install specific branches with custom names
- **Dependency management**: Automatic checking and installation of system and gitpm dependencies
- **Script execution**: Automatic execution of setup, update, check, and removal scripts
- **User/System installs**: Support for both user (`~/.local/share/apps`) and system (`/opt/apps`) installations
- **Update checking**: Check for updates with custom scripts or git commit comparison
- **Compatibility checking**: Ensures repositories are marked as gitpm-compatible

## Installation

1. Make the script executable:
```bash
chmod +x gitpm.py
```

2. Optionally move it to your PATH:
```bash
sudo cp gitpm.py /usr/local/bin/gitpm
```

## Configuration

### Repository Configuration

Create config files to list available repositories. GitPM will automatically load all files matching `repos*.conf` from:

- **User config**: `~/.config/gitpm/repos*.conf`
- **System config**: `/etc/xdg/gitpm/repos*.conf`

#### Config File Format

Each line in the config file can be:
- Simple URL: `https://github.com/user/repo.git`
- With branch: `https://github.com/user/repo.git,branch-name`
- With branch and custom name: `https://github.com/user/repo.git,branch-name,custom-name`

**Examples:**
```
# Simple format
https://github.com/user/app1.git

# With branch
https://github.com/user/app1.git,develop

# With branch and custom name (allows multiple installs from same repo)
https://github.com/user/app1.git,develop,dev-version
https://github.com/user/app1.git,main,stable-version

# SSH format
git@github.com:user/app2.git

# Short format (assumes GitHub)
user/repo
```

### Repository Compatibility

Repositories must include a marker file to be considered compatible:
- `.gitpm` (empty file is fine)
- `gitpm.json` (can contain metadata)
- `.gitpm.json` (can contain metadata)

Use `--force` flag to skip compatibility check and install anyway.

### Package Metadata (gitpm.json)

Repositories can include a `gitpm.json` file with dependency information:

```json
{
  "system_only": false,
  "dependencies": {
    "system": {
      "method": "sudo pacman -S --noconfirm",
      "check_commands": [
        ["docker", "podman"],
        "docker-compose",
        "distrobox"
      ],
      "Arch": {
        "docker": ["docker", "podman"],
        "docker-compose": "docker-compose",
        "distrobox": "distrobox"
      },
      "Debian": {
        "docker": ["docker.io", "podman"],
        "docker-compose": "docker-compose-plugin",
        "distrobox": "distrobox"
      },
      "Ubuntu": {
        "docker": "docker.io",
        "docker-compose": "docker-compose-plugin",
        "distrobox": "distrobox"
      },
      "Fedora": {
        "docker": "docker",
        "docker-compose": "docker-compose",
        "distrobox": "distrobox"
      },
      "Fedora_method": "sudo dnf install -y"
    },
    "gitpm": [
      "https://github.com/user/dependency1.git",
      "https://github.com/user/dependency2.git,branch,custom-name"
    ]
  }
}
```

#### Fields

- **`system_only`**: If `true`, package can only be installed system-wide (requires `--system` flag)
- **`dependencies.system`**: System package dependencies
  - **`check_commands`**: Maps commands to check (e.g., `"docker"`) to package names that provide them
    - Arrays indicate multiple packages can provide the same command (e.g., `["docker", "podman"]`)
    - GitPM checks if the command exists (using `-v` flag), not the package name
  - **Distro sections** (Arch, Debian, Fedora, etc.): Maps command names to distro-specific package names
    - Example: `"docker": "docker.io"` on Debian means the `docker` command comes from the `docker.io` package
    - This allows the same command check across distros while using correct package names per distro
  - **`method`**: Install command (e.g., `"sudo pacman -S --noconfirm"`)
  - **`{Distro}_method`**: Per-distro install method override
  - **Legacy format**: Arrays are still supported for backward compatibility
- **`dependencies.gitpm`**: GitPM package dependencies (same format as repos.conf)

## Usage

### Install a Package

```bash
# User install (default)
./gitpm.py install appname

# System install (requires root)
sudo ./gitpm.py --system install appname

# Skip compatibility check
./gitpm.py install appname --force
```

### Update Packages

```bash
# Update all packages
./gitpm.py update

# Update specific package
./gitpm.py update appname

# Check for updates without applying them
./gitpm.py update --check
./gitpm.py update appname --check
```

### Remove a Package

```bash
./gitpm.py remove appname
```

### List Packages

```bash
# List all (installed and available)
./gitpm.py list

# List only installed
./gitpm.py list --installed

# List only available
./gitpm.py list --available

# Search packages
./gitpm.py list --search query

# Show which config file each package comes from
./gitpm.py list --show-source
```

## Scripts

Repositories can include scripts that are automatically executed during operations. Scripts are checked in this order:
1. User/system-specific scripts (e.g., `setup-user.sh`, `update-system.py`)
2. Generic scripts (e.g., `setup.sh`, `update.py`)

### Setup Scripts

Run during installation:
- `setup-user.sh`, `install-user.sh`, `setup-user.py`, `install-user.py`
- `setup-system.sh`, `install-system.sh`, `setup-system.py`, `install-system.py`
- `setup.sh`, `install.sh`, `setup.py`, `install.py`

### Update Scripts

Run when updating a package:
- `update-user.sh`, `upgrade-user.sh`, `update-user.py`, `upgrade-user.py`
- `update-system.sh`, `upgrade-system.sh`, `update-system.py`, `upgrade-system.py`
- `update.sh`, `upgrade.sh`, `update.py`, `upgrade.py`

If no update script exists, the setup script is re-run as fallback.

### Check Scripts

Run when checking for updates (`--check` flag):
- `check-user.sh`, `check-updates-user.sh`, `check-user.py`, `check-updates-user.py`
- `check-system.sh`, `check-updates-system.sh`, `check-system.py`, `check-updates-system.py`
- `check.sh`, `check-updates.sh`, `check.py`, `check-updates.py`

**Exit codes:**
- `0` = No updates available
- `1` = Updates available
- Other = Error (falls back to git commit comparison)

### Removal Scripts

Run when removing a package:
- `remove-user.sh`, `uninstall-user.sh`, `remove-user.py`, `uninstall-user.py`
- `remove-system.sh`, `uninstall-system.sh`, `remove-system.py`, `uninstall-system.py`
- `remove.sh`, `uninstall.sh`, `remove.py`, `uninstall.py`

## Dependency Management

### System Dependencies

GitPM automatically:
- Checks if system packages are installed (using `-v` flag)
- Supports alternative packages (e.g., docker OR podman)
- Attempts to install missing packages if:
  - Installing as system (`--system` flag)
  - User has sudo access (for user installs)

Package names and install methods are distro-specific. GitPM detects your distribution (Arch, Debian, Fedora, etc.) and uses the appropriate package list.

### GitPM Dependencies

GitPM dependencies are automatically installed before the parent package. They use the same install type (user/system) as the parent package.

If a dependency requires system install (`system_only: true`), the parent package must also be installed with `--system`.

## Installation Locations

- **User installs**: `~/.local/share/apps/{package-name}`
- **System installs**: `/opt/apps/{package-name}`

Registry files:
- **User**: `~/.config/gitpm/installed.json`
- **System**: `/etc/gitpm/installed.json`

## Examples

### Basic Installation

```bash
# Add repository to config
echo "https://github.com/user/myapp.git" >> ~/.config/gitpm/repos.conf

# Install
./gitpm.py install myapp
```

### Multiple Branches from Same Repo

```bash
# In repos.conf:
https://github.com/user/app.git,develop,dev-version
https://github.com/user/app.git,main,stable-version

# Install both
./gitpm.py install dev-version
./gitpm.py install stable-version
```

### Package with Dependencies

Create `gitpm.json` in your repository:
```json
{
  "dependencies": {
    "system": {
      "method": "sudo pacman -S --noconfirm",
      "Arch": ["python", "git"]
    },
    "gitpm": [
      "https://github.com/user/required-tool.git"
    ]
  }
}
```

GitPM will automatically install dependencies before installing your package.

### System-Only Package

```json
{
  "system_only": true,
  "dependencies": {
    "system": {
      "Arch": ["systemd"]
    }
  }
}
```

This package can only be installed with `sudo ./gitpm.py --system install package-name`.

## Troubleshooting

### "Repository is not marked as gitpm-compatible"

Add one of these marker files to your repository root:
- `.gitpm`
- `gitpm.json`
- `.gitpm.json`

Or use `--force` flag to skip the check.

### "Missing system packages and cannot install them"

Install the required packages manually, or install with `--system` flag if you have root access.

### "Branch not found"

Verify the branch name exists in the repository. Branch names with slashes (e.g., `feat/new-feature`) are supported.

### Dependency installation fails

Check that:
- Install method in `gitpm.json` is correct for your distribution
- Package names are correct for your distribution
- You have necessary permissions (sudo for user installs, root for system installs)

## License

This tool is provided as-is for managing git-based package installations.

