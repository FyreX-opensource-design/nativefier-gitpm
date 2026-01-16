#!/usr/bin/env python3
"""
Git Package Manager - Install and manage applications from git repositories
"""
import os
import sys
import json
import argparse
import subprocess
import re
from pathlib import Path
from urllib.parse import urlparse
from typing import List, Dict, Optional, Tuple

class GitPackageManager:
    def __init__(self, system: bool = False):
        self.system = system
        if system:
            self.apps_dir = Path("/opt/apps")
            self.config_dir = Path("/etc/gitpm")
            self.installed_file = Path("/etc/gitpm/installed.json")
        else:
            self.apps_dir = Path.home() / ".local/share/apps"
            self.config_dir = Path.home() / ".config/gitpm"
            self.installed_file = self.config_dir / "installed.json"
        
        # Ensure directories exist
        self.apps_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # Load installed apps
        self.installed = self.load_installed()
        
        # Detect distribution
        self.distro = self.detect_distro()
    
    def load_config(self) -> List[Dict[str, str]]:
        """Load git repositories from config file(s)
        Scans for all repos*.conf files in:
        - System config: /etc/xdg/gitpm/repos*.conf
        - User config: ~/.config/gitpm/repos*.conf (or system config if --system flag)
        Returns list of dicts with keys: url, branch, name
        Format: url,branch,name (branch and name are optional)
        """
        import glob
        
        config_files = []
        
        # Load system configs from /etc/xdg/gitpm (always check this)
        system_xdg_dir = Path("/etc/xdg/gitpm")
        if system_xdg_dir.exists():
            system_pattern = str(system_xdg_dir / "repos*.conf")
            system_configs = sorted(glob.glob(system_pattern))
            config_files.extend(system_configs)
            
            # Also check for default repos.conf
            default_system = system_xdg_dir / "repos.conf"
            if default_system.exists() and str(default_system) not in config_files:
                config_files.append(str(default_system))
        
        # Load user configs (unless system mode)
        if not self.system:
            user_config_dir = Path.home() / ".config/gitpm"
            if user_config_dir.exists():
                user_pattern = str(user_config_dir / "repos*.conf")
                user_configs = sorted(glob.glob(user_pattern))
                config_files.extend(user_configs)
                
                # Also check for default repos.conf
                default_user = user_config_dir / "repos.conf"
                if default_user.exists() and str(default_user) not in config_files:
                    config_files.append(str(default_user))
        else:
            # In system mode, also check /etc/gitpm
            system_dir = Path("/etc/gitpm")
            if system_dir.exists():
                system_pattern = str(system_dir / "repos*.conf")
                system_configs = sorted(glob.glob(system_pattern))
                config_files.extend(system_configs)
                
                default_system = system_dir / "repos.conf"
                if default_system.exists() and str(default_system) not in config_files:
                    config_files.append(str(default_system))
        
        if not config_files:
            print(f"Error: No config files found")
            print(f"Please create a config file in one of these locations:")
            print(f"  - {Path.home() / '.config/gitpm/repos.conf'} (user)")
            print(f"  - /etc/xdg/gitpm/repos.conf (system)")
            print(f"Format: url or url,branch,name")
            sys.exit(1)
        
        repos = []
        for config_file in config_files:
            try:
                config_path = Path(config_file)
                # Determine if it's a system or user config
                is_system = str(config_path).startswith('/etc')
                source_label = f"[system]{config_path.name}" if is_system else config_path.name
                
                with open(config_file, 'r') as f:
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        if line and not line.startswith('#'):
                            # Parse format: url,branch,name
                            parts = [p.strip() for p in line.split(',')]
                            if not parts[0]:  # Skip empty URLs
                                continue
                            repo_entry = {
                                'url': parts[0],
                                'branch': parts[1] if len(parts) > 1 and parts[1] else None,
                                'name': parts[2] if len(parts) > 2 and parts[2] else None,
                                'source_file': source_label  # Track which file it came from
                            }
                            repos.append(repo_entry)
            except IOError as e:
                print(f"Warning: Could not read config file {config_file}: {e}", file=sys.stderr)
                continue
        
        return repos
    
    def parse_repo_url(self, url: str) -> Tuple[str, str, str]:
        """Parse git URL to extract user/org and repo name
        Returns: (full_url, user/org, repo_name)
        """
        # Handle various git URL formats
        url = url.strip()
        
        # Remove .git suffix if present
        if url.endswith('.git'):
            url = url[:-4]
        
        # Parse URL
        if url.startswith('http://') or url.startswith('https://'):
            parsed = urlparse(url)
            path_parts = parsed.path.strip('/').split('/')
            if len(path_parts) >= 2:
                user = path_parts[0]
                repo = path_parts[1]
                full_url = f"{parsed.scheme}://{parsed.netloc}/{user}/{repo}.git"
                return (full_url, user, repo)
        elif url.startswith('git@'):
            # SSH format: git@github.com:user/repo.git
            match = re.match(r'git@([^:]+):([^/]+)/([^/]+)', url)
            if match:
                host, user, repo = match.groups()
                full_url = f"git@{host}:{user}/{repo}.git"
                return (full_url, user, repo)
        elif '/' in url and not url.startswith('http'):
            # Short format: user/repo
            parts = url.split('/')
            if len(parts) == 2:
                user, repo = parts
                full_url = f"https://github.com/{user}/{repo}.git"
                return (full_url, user, repo)
        
        # Fallback: assume it's a valid git URL
        # Try to extract repo name from URL
        repo_name = url.split('/')[-1].replace('.git', '')
        return (url, 'unknown', repo_name)
    
    def find_repos_by_name(self, name: str) -> List[Dict[str, str]]:
        """Find all repos with matching name from config
        Matches by custom name if provided, otherwise by repo name
        """
        repos = self.load_config()
        matches = []
        
        for repo_entry in repos:
            repo_url = repo_entry['url']
            _, user, repo_name = self.parse_repo_url(repo_url)
            
            # Use custom name if provided, otherwise use repo name
            display_name = repo_entry['name'] if repo_entry['name'] else repo_name
            
            if display_name.lower() == name.lower():
                matches.append({
                    'url': repo_url,
                    'user': user,
                    'name': display_name,
                    'repo_name': repo_name,
                    'branch': repo_entry['branch']
                })
        
        return matches
    
    def prompt_selection(self, options: List[Dict[str, str]], prompt_text: str) -> Optional[Dict[str, str]]:
        """Prompt user to select from a list of options"""
        if len(options) == 0:
            return None
        if len(options) == 1:
            return options[0]
        
        print(f"\n{prompt_text}")
        print("-" * 80)
        for i, option in enumerate(options, 1):
            branch_info = f" [branch: {option.get('branch', 'default')}]" if option.get('branch') else ""
            print(f"{i}. {option['user']}/{option['name']}{branch_info}")
            print(f"   {option['url']}")
        print("-" * 80)
        
        while True:
            try:
                choice = input(f"Select (1-{len(options)}): ").strip()
                idx = int(choice) - 1
                if 0 <= idx < len(options):
                    return options[idx]
                else:
                    print(f"Please enter a number between 1 and {len(options)}")
            except (ValueError, KeyboardInterrupt):
                print("\nCancelled.")
                return None
    
    def check_scripts(self, repo_path: Path) -> Dict[str, Optional[Path]]:
        """Check for setup, removal, and update scripts in repo
        Checks for user/system-specific scripts first, then falls back to generic ones
        """
        scripts = {
            'setup': None,
            'remove': None,
            'uninstall': None,
            'update': None,
            'check': None
        }
        
        # Determine script prefix based on install type
        prefix = 'system' if self.system else 'user'
        
        # Script names: check specific ones first, then generic
        script_names = {
            'setup': [
                # User/system specific
                f'setup-{prefix}.sh', f'install-{prefix}.sh',
                f'setup-{prefix}.py', f'install-{prefix}.py',
                # Generic
                'setup.sh', 'install.sh', 'setup.py', 'install.py'
            ],
            'remove': [
                # User/system specific
                f'remove-{prefix}.sh', f'uninstall-{prefix}.sh',
                f'remove-{prefix}.py', f'uninstall-{prefix}.py',
                # Generic
                'remove.sh', 'uninstall.sh', 'remove.py', 'uninstall.py'
            ],
            'update': [
                # User/system specific
                f'update-{prefix}.sh', f'upgrade-{prefix}.sh',
                f'update-{prefix}.py', f'upgrade-{prefix}.py',
                # Generic
                'update.sh', 'upgrade.sh', 'update.py', 'upgrade.py'
            ],
            'check': [
                # User/system specific
                f'check-{prefix}.sh', f'check-updates-{prefix}.sh',
                f'check-{prefix}.py', f'check-updates-{prefix}.py',
                # Generic
                'check.sh', 'check-updates.sh', 'check.py', 'check-updates.py'
            ]
        }
        
        for script_type, names in script_names.items():
            for name in names:
                script_path = repo_path / name
                if script_path.exists() and script_path.is_file():
                    # Make script executable if it's a shell script
                    if script_path.suffix in ['.sh', '']:
                        try:
                            os.chmod(script_path, 0o755)
                        except Exception:
                            pass  # Ignore permission errors
                    # Check if executable or if it's a Python script
                    if script_path.suffix == '.py' or os.access(script_path, os.X_OK):
                        scripts[script_type] = script_path
                        break
        
        return scripts
    
    def run_script(self, script_path: Path, repo_path: Path, return_exit_code: bool = False):
        """Run a setup or removal script
        If return_exit_code is True, returns the exit code (int) instead of bool
        Returns: bool (success/failure) or int (exit code) if return_exit_code=True
        """
        try:
            # Ensure script is executable (for shell scripts)
            if script_path.suffix in ['.sh', '']:
                try:
                    os.chmod(script_path, 0o755)
                except Exception:
                    pass  # Ignore permission errors, will use bash to run it
            
            if script_path.suffix == '.py':
                cmd = [sys.executable, str(script_path)]
            else:
                cmd = ['bash', str(script_path)]
            
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                check=False,  # Don't raise on non-zero exit
                capture_output=True,
                text=True
            )
            
            if result.stdout:
                print(result.stdout)
            if result.stderr and result.returncode != 0:
                print(result.stderr, file=sys.stderr)
            
            if return_exit_code:
                return result.returncode
            
            # For regular scripts, only 0 is success
            return result.returncode == 0
        except Exception as e:
            print(f"Error running script {script_path}: {e}", file=sys.stderr)
            if return_exit_code:
                return 255  # Error code
            return False
    
    def load_installed(self) -> Dict[str, Dict]:
        """Load installed apps registry"""
        if not self.installed_file.exists():
            return {}
        
        try:
            with open(self.installed_file, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    
    def save_installed(self):
        """Save installed apps registry"""
        with open(self.installed_file, 'w') as f:
            json.dump(self.installed, f, indent=2)
    
    def detect_distro(self) -> str:
        """Detect base Linux distribution (Arch, Fedora, Debian, etc.)
        Checks ID_LIKE first to get the base distro, then falls back to ID
        This ensures Arch-based distros (Garuda, Catchy, etc.) are detected as "Arch"
        """
        try:
            # Check /etc/os-release first (most reliable)
            if Path('/etc/os-release').exists():
                distro_id = None
                distro_id_like = None
                
                with open('/etc/os-release', 'r') as f:
                    for line in f:
                        if line.startswith('ID_LIKE='):
                            # ID_LIKE contains the base distribution(s)
                            # e.g., "arch" for Garuda, "debian" for Linux Mint
                            distro_id_like = line.split('=', 1)[1].strip().strip('"').strip("'")
                            # ID_LIKE can be space-separated, take the first one
                            if ' ' in distro_id_like:
                                distro_id_like = distro_id_like.split()[0]
                        elif line.startswith('ID='):
                            distro_id = line.split('=', 1)[1].strip().strip('"').strip("'")
                
                # Prefer ID_LIKE (base distro) over ID (specific OS)
                # This ensures Garuda/Catchy -> Arch, Linux Mint -> Debian, etc.
                distro_to_check = distro_id_like if distro_id_like else distro_id
                
                if distro_to_check:
                    # Normalize common distribution names
                    distro_map = {
                        'arch': 'Arch',
                        'archlinux': 'Arch',
                        'debian': 'Debian',
                        'ubuntu': 'Ubuntu',
                        'fedora': 'Fedora',
                        'rhel': 'RHEL',
                        'centos': 'CentOS',
                        'opensuse': 'openSUSE',
                        'sles': 'SLES',
                        'suse': 'openSUSE'
                    }
                    return distro_map.get(distro_to_check.lower(), distro_to_check.capitalize())
            
            # Fallback: check for distro-specific files
            if Path('/etc/arch-release').exists():
                return 'Arch'
            elif Path('/etc/debian_version').exists():
                return 'Debian'
            elif Path('/etc/fedora-release').exists():
                return 'Fedora'
            elif Path('/etc/redhat-release').exists():
                return 'RHEL'
            elif Path('/etc/SuSE-release').exists():
                return 'openSUSE'
            
            return 'Unknown'
        except Exception:
            return 'Unknown'
    
    def load_gitpm_json(self, repo_path: Path) -> Tuple[Optional[Dict], Optional[str]]:
        """Load gitpm.json from repository
        Returns: (json_data, error_message)
        If JSON is invalid, returns (None, error_message)
        """
        marker_files = ['gitpm.json', '.gitpm.json']
        
        for marker_file in marker_files:
            json_path = repo_path / marker_file
            if json_path.exists() and json_path.is_file():
                try:
                    with open(json_path, 'r') as f:
                        return json.load(f), None
                except json.JSONDecodeError as e:
                    error_msg = f"Invalid JSON in {marker_file}: {e}"
                    return None, error_msg
                except Exception as e:
                    error_msg = f"Error reading {marker_file}: {e}"
                    return None, error_msg
        
        return None, None
    
    def check_system_package(self, package: str) -> bool:
        """Check if a system package/command is installed using -v flag"""
        try:
            # Try running the command with -v flag
            result = subprocess.run(
                [package, '-v'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5
            )
            # If it returns 0, the command exists
            # If it returns non-zero but has output, it might still exist (some commands use -v differently)
            if result.returncode == 0:
                return True
            # Some commands output version to stderr
            if result.stderr and (b'version' in result.stderr.lower() or b'Version' in result.stderr):
                return True
            # Check if command exists in PATH
            which_result = subprocess.run(
                ['which', package],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=2
            )
            return which_result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # Check if command exists in PATH
            try:
                which_result = subprocess.run(
                    ['which', package],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=2
                )
                return which_result.returncode == 0
            except Exception:
                return False
        except Exception:
            return False
    
    def check_package_alternatives(self, alternatives: List[str]) -> Tuple[bool, Optional[str]]:
        """Check if any of the alternative packages are installed
        Returns: (is_installed, installed_package_name)
        """
        for package in alternatives:
            if self.check_system_package(package):
                return True, package
        return False, None
    
    def check_system_dependencies(self, dependencies: Dict) -> Tuple[bool, List[str], str]:
        """Check system package dependencies
        Returns: (all_satisfied, missing_packages, install_method)
        """
        missing = []
        install_method = ''
        
        # Get install method (can be global or per-distro)
        if 'method' in dependencies:
            install_method = dependencies['method']
        elif f'{self.distro}_method' in dependencies:
            install_method = dependencies[f'{self.distro}_method']
        
        # Check if using new format with check_commands
        check_commands = dependencies.get('check_commands', [])
        distro_packages = dependencies.get(self.distro, {})
        
        if check_commands and isinstance(check_commands, list) and isinstance(distro_packages, dict):
            # New format: check_commands is a list of commands to check
            # Can be strings or arrays of alternatives (e.g., ["docker"] or [["docker", "podman"]])
            # distro_packages maps command names to package names for this distro
            for command_entry in check_commands:
                if isinstance(command_entry, list):
                    # Array of alternative commands (e.g., ["docker", "podman"])
                    # Check if any of these commands exist
                    is_installed, installed_cmd = self.check_package_alternatives(command_entry)
                    if not is_installed:
                        # None of the alternative commands exist, need to install
                        # Use first command to look up package in distro section
                        primary_command = command_entry[0]
                        if primary_command in distro_packages:
                            pkg_entry = distro_packages[primary_command]
                            if isinstance(pkg_entry, list):
                                missing.append(pkg_entry[0])
                            elif isinstance(pkg_entry, str):
                                missing.append(pkg_entry)
                            else:
                                missing.append(str(pkg_entry))
                        else:
                            # No package mapping, use first command as package name
                            missing.append(primary_command)
                elif isinstance(command_entry, str):
                    # Single command to check
                    command_found = self.check_system_package(command_entry)
                    if not command_found:
                        # Command not found, look up package in distro section
                        if command_entry in distro_packages:
                            pkg_entry = distro_packages[command_entry]
                            if isinstance(pkg_entry, list):
                                missing.append(pkg_entry[0])
                            elif isinstance(pkg_entry, str):
                                missing.append(pkg_entry)
                            else:
                                missing.append(str(pkg_entry))
                        else:
                            # Command in check list but no package mapping for this distro
                            missing.append(command_entry)
        elif check_commands and isinstance(check_commands, dict):
            # Legacy format: check_commands as dict (backward compatibility)
            for command, package_names in check_commands.items():
                # Check if command exists
                if not self.check_system_package(command):
                    # Command not found, need to install one of the packages
                    if isinstance(package_names, list):
                        # Multiple packages can provide this command
                        # Check which package name to use for this distro
                        distro_pkg = None
                        for pkg_name in package_names:
                            if pkg_name in distro_packages:
                                distro_pkg = distro_packages[pkg_name]
                                break
                        if distro_pkg:
                            missing.append(distro_pkg)
                        else:
                            # Fallback: use first package name
                            missing.append(package_names[0])
                    else:
                        # Single package provides this command
                        if package_names in distro_packages:
                            missing.append(distro_packages[package_names])
                        else:
                            missing.append(package_names)
        elif self.distro in dependencies:
            # Old format: list of packages
            distro_deps = dependencies[self.distro]
            if isinstance(distro_deps, list):
                for dep_entry in distro_deps:
                    if isinstance(dep_entry, str):
                        # Simple package name
                        if not self.check_system_package(dep_entry):
                            missing.append(dep_entry)
                    elif isinstance(dep_entry, list):
                        # Alternative packages (e.g., [docker, podman])
                        is_installed, installed_pkg = self.check_package_alternatives(dep_entry)
                        if not is_installed:
                            missing.append(f"({' or '.join(dep_entry)})")
            elif isinstance(distro_deps, dict):
                # Dict format but no check_commands - check each package directly
                for pkg_name, pkg_value in distro_deps.items():
                    if isinstance(pkg_value, str):
                        if not self.check_system_package(pkg_value):
                            missing.append(pkg_value)
        
        # Check if we can install packages
        has_sudo = False
        if missing:
            # Check if user has sudo access
            sudo_check = subprocess.run(
                ['sudo', '-n', 'true'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=2
            )
            has_sudo = sudo_check.returncode == 0 or os.geteuid() == 0
        
        return len(missing) == 0, missing, install_method
    
    def check_gitpm_dependencies(self, gitpm_deps: List[str]) -> Tuple[bool, List[str], List[Dict], List[str]]:
        """Check gitpm package dependencies
        Returns: (all_satisfied, missing_packages, dependency_info, system_only_deps)
        """
        missing = []
        dep_info = []
        system_only_deps = []
        
        for dep in gitpm_deps:
            # Parse dependency (can be in repos.conf format: url,branch,name)
            parts = [p.strip() for p in dep.split(',')]
            if len(parts) > 2 and parts[2]:
                dep_name = parts[2]
                dep_url = parts[0]
                dep_branch = parts[1] if len(parts) > 1 and parts[1] else None
            else:
                # Extract name from URL
                _, _, repo_name = self.parse_repo_url(parts[0])
                dep_name = repo_name
                dep_url = parts[0]
                dep_branch = parts[1] if len(parts) > 1 and parts[1] else None
            
            # Check if dependency is installed
            if dep_name not in self.installed:
                missing.append(dep_name)
                dep_info.append({
                    'name': dep_name,
                    'url': dep_url,
                    'branch': dep_branch
                })
                
                # Check if dependency requires system install
                # We need to check the dependency's gitpm.json to see if it's system_only
                # For now, we'll check this when we try to install it
            else:
                # Dependency is installed, check if it requires system but we're doing user install
                if not self.system:
                    # Check the installed dependency's gitpm.json
                    dep_path = Path(self.installed[dep_name]['path'])
                    dep_json, _ = self.load_gitpm_json(dep_path)
                    if dep_json and dep_json.get('system_only', False):
                        system_only_deps.append(dep_name)
        
        return len(missing) == 0, missing, dep_info, system_only_deps
    
    def check_dependencies(self, repo_path: Path) -> Tuple[bool, List[str], List[str], bool, List[Dict], Optional[str]]:
        """Check all dependencies for a repository
        Returns: (all_satisfied, missing_system, missing_gitpm, can_install_system, gitpm_dep_info, json_error)
        """
        gitpm_json, json_error = self.load_gitpm_json(repo_path)
        
        if json_error:
            # Invalid JSON - return error
            return False, [], [], False, [], json_error
        
        if not gitpm_json:
            # No dependencies defined
            return True, [], [], False, [], None
        
        missing_system = []
        missing_gitpm = []
        can_install_system = False
        gitpm_dep_info = []
        
        # Check if dependencies section exists
        if 'dependencies' not in gitpm_json:
            # No dependencies section
            return True, [], [], False, [], None
        
        # Check system dependencies
        install_method = ''
        if 'system' in gitpm_json['dependencies']:
            all_satisfied, missing, method = self.check_system_dependencies(
                gitpm_json['dependencies']['system']
            )
            missing_system = missing
            install_method = method
            
            # Check if we can install system packages
            if missing_system and self.system:
                can_install_system = True  # System installs can always install deps
            elif missing_system and not self.system:
                # Check if user has sudo
                sudo_check = subprocess.run(
                    ['sudo', '-n', 'true'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=2
                )
                can_install_system = sudo_check.returncode == 0 or os.geteuid() == 0
        
        # Check gitpm dependencies (only if 'gitpm' key exists)
        system_only_deps = []
        if 'gitpm' in gitpm_json['dependencies']:
            all_satisfied_gitpm, missing, dep_info, system_only = self.check_gitpm_dependencies(
                gitpm_json['dependencies']['gitpm']
            )
            missing_gitpm = missing
            gitpm_dep_info = dep_info
            system_only_deps = system_only
        
        # Check if current package requires system install
        if gitpm_json.get('system_only', False) and not self.system:
            return False, [], [], False, [], "This package requires system-wide installation (use --system flag)"
        
        # Check if any installed dependencies require system install but we're doing user install
        if system_only_deps and not self.system:
            deps_list = ', '.join(system_only_deps)
            return False, [], [], False, [], f"Installed dependencies require system install: {deps_list}. This package must be installed with --system flag."
        
        all_satisfied = len(missing_system) == 0 and len(missing_gitpm) == 0
        
        return all_satisfied, missing_system, missing_gitpm, can_install_system, gitpm_dep_info, None
    
    def install_system_packages(self, missing: List[str], dependencies: Dict, install_method: str) -> bool:
        """Install missing system packages"""
        try:
            # missing already contains the package names to install
            # Remove duplicates and clean up
            packages_to_install = list(set([pkg.strip('()') for pkg in missing if pkg.strip()]))
            
            if not packages_to_install:
                return True  # Nothing to install
            
            # Parse install method (e.g., "sudo pacman -S --noconfirm")
            install_cmd = install_method.split()
            # Append package names to the install command
            install_cmd.extend(packages_to_install)
            
            print(f"Running: {' '.join(install_cmd)}")
            result = subprocess.run(
                install_cmd,
                check=True,
                timeout=300  # 5 minute timeout
            )
            return result.returncode == 0
        except subprocess.CalledProcessError as e:
            print(f"Error installing packages: {e}", file=sys.stderr)
            return False
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return False
    
    def verify_repo(self, repo_url: str, branch: Optional[str] = None) -> Tuple[bool, str]:
        """Verify that a repository exists and is accessible
        If branch is specified, also verify that branch exists
        Returns: (is_valid, error_message)
        """
        try:
            # Use git ls-remote to check if repository exists and is accessible
            result = subprocess.run(
                ['git', 'ls-remote', '--heads', '--tags', repo_url],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                if "not found" in error_msg.lower() or "does not exist" in error_msg.lower():
                    return False, f"Repository not found or not accessible: {error_msg}"
                elif "permission denied" in error_msg.lower() or "authentication" in error_msg.lower():
                    return False, f"Permission denied or authentication required: {error_msg}"
                else:
                    return False, f"Error accessing repository: {error_msg}"
            
            # If branch is specified, verify it exists
            if branch:
                # Check if branch exists in the remote
                # ls-remote output format: <commit_hash>\trefs/heads/<branch_name>
                remote_refs = result.stdout
                # Look for exact branch match (handles branches with slashes)
                branch_refs = []
                for line in remote_refs.split('\n'):
                    if not line.strip():
                        continue
                    # Extract the ref part (after the tab)
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        ref = parts[1]
                        # Check for exact branch match
                        if ref == f'refs/heads/{branch}':
                            branch_refs.append(line)
                
                if not branch_refs:
                    # Also check for tags in case branch name matches a tag
                    tag_refs = []
                    for line in remote_refs.split('\n'):
                        if not line.strip():
                            continue
                        parts = line.split('\t')
                        if len(parts) >= 2:
                            ref = parts[1]
                            if ref == f'refs/tags/{branch}':
                                tag_refs.append(line)
                    
                    if not tag_refs:
                        return False, f"Branch '{branch}' not found in repository"
                    else:
                        return False, f"'{branch}' exists as a tag, not a branch. Please use a branch name."
            
            return True, ""
            
        except subprocess.TimeoutExpired:
            return False, "Timeout while checking repository (network may be slow or repository unreachable)"
        except FileNotFoundError:
            return False, "Git is not installed or not in PATH"
        except Exception as e:
            return False, f"Unexpected error while verifying repository: {str(e)}"
    
    def check_repo_compatibility(self, repo_url: str, branch: Optional[str] = None) -> Tuple[bool, str]:
        """Check if repository is compatible with gitpm
        Looks for a marker file (.gitpm, gitpm.json, or .gitpm.json) in the repository root
        Uses a shallow clone to a temp directory to check for the marker file
        Returns: (is_compatible, error_message)
        """
        import tempfile
        import shutil
        
        # Marker files that indicate gitpm compatibility
        marker_files = ['.gitpm', 'gitpm.json', '.gitpm.json']
        
        temp_dir = None
        try:
            # Create a temporary directory for shallow clone
            temp_dir = tempfile.mkdtemp(prefix='gitpm_check_')
            temp_repo_path = Path(temp_dir) / "repo"
            
            # Do a shallow clone (depth=1) to check files
            clone_cmd = ['git', 'clone', '--depth', '1', '--no-checkout', repo_url, str(temp_repo_path)]
            if branch:
                clone_cmd.extend(['--branch', branch])
            
            clone_result = subprocess.run(
                clone_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30
            )
            
            if clone_result.returncode != 0:
                # If shallow clone fails, try without branch specification
                if branch:
                    clone_cmd = ['git', 'clone', '--depth', '1', '--no-checkout', repo_url, str(temp_repo_path)]
                    clone_result = subprocess.run(
                        clone_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=30
                    )
                
                if clone_result.returncode != 0:
                    return False, f"Could not check compatibility: {clone_result.stderr[:100]}"
            
            # Checkout just the files we need to inspect
            checkout_result = subprocess.run(
                ['git', 'checkout', 'HEAD', '--'],
                cwd=temp_repo_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10
            )
            
            # Check for marker file in root directory
            if temp_repo_path.exists():
                for marker in marker_files:
                    marker_path = temp_repo_path / marker
                    if marker_path.exists() and marker_path.is_file():
                        return True, ""
            
            # No marker file found
            marker_list = ', '.join(marker_files)
            return False, f"Repository is not marked as gitpm-compatible (missing marker file: {marker_list})"
            
        except subprocess.TimeoutExpired:
            return False, "Timeout while checking repository compatibility"
        except Exception as e:
            return False, f"Error checking compatibility: {str(e)}"
        finally:
            # Clean up temporary directory
            if temp_dir and Path(temp_dir).exists():
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass  # Ignore cleanup errors
    
    def install(self, name: str, skip_compatibility_check: bool = False, skip_dependency_check: bool = False) -> bool:
        """Install a package by name"""
        # Find matching repos
        matches = self.find_repos_by_name(name)
        
        if not matches:
            print(f"Error: No repository found with name '{name}'")
            return False
        
        # Handle duplicates
        selected = self.prompt_selection(
            matches,
            f"Multiple repositories found with name '{name}':"
        )
        
        if not selected:
            print("Installation cancelled.")
            return False
        
        repo_url = selected['url']
        branch = selected.get('branch')
        display_name = selected['name']  # Custom name or repo name
        _, user, repo_name = self.parse_repo_url(repo_url)
        
        # Use custom name for folder if provided, otherwise use repo name
        install_name = display_name
        repo_path = self.apps_dir / install_name
        
        # Check if already installed
        if install_name in self.installed:
            print(f"'{install_name}' is already installed at {self.installed[install_name]['path']}")
            response = input("Reinstall? (y/N): ").strip().lower()
            if response != 'y':
                return False
            # Remove existing installation
            self.remove(install_name, skip_uninstall=True)
        
        # Verify repository before cloning
        print(f"Verifying repository {repo_url}...")
        is_valid, error_msg = self.verify_repo(repo_url, branch)
        if not is_valid:
            print(f"Error: {error_msg}", file=sys.stderr)
            return False
        
        branch_info = f" (branch: {branch})" if branch else ""
        print(f"Repository verified{branch_info}")
        
        # Check repository compatibility
        if not skip_compatibility_check:
            print(f"Checking repository compatibility...")
            is_compatible, compat_msg = self.check_repo_compatibility(repo_url, branch)
            if not is_compatible:
                print(f"Error: {compat_msg}", file=sys.stderr)
                print(f"\nTo make a repository compatible with gitpm, add one of these marker files to the root:", file=sys.stderr)
                print(f"  - .gitpm", file=sys.stderr)
                print(f"  - gitpm.json", file=sys.stderr)
                print(f"  - .gitpm.json", file=sys.stderr)
                print(f"\nUse --force flag to skip compatibility check and install anyway.", file=sys.stderr)
                return False
            print("Repository is compatible with gitpm")
        
        # Clone repository
        print(f"Cloning {repo_url} to {repo_path}...")
        cloned = False
        try:
            # Clone the repository
            clone_cmd = ['git', 'clone', repo_url, str(repo_path)]
            subprocess.run(
                clone_cmd,
                check=True,
                capture_output=True
            )
            cloned = True
            
            # Checkout specific branch if provided
            if branch:
                print(f"Checking out branch '{branch}'...")
                try:
                    # Fetch all branches first to get remote branch info
                    subprocess.run(
                        ['git', 'fetch', 'origin'],
                        cwd=repo_path,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True
                    )
                    
                    # Check if branch exists locally first
                    local_branches = subprocess.run(
                        ['git', 'branch', '--list', branch],
                        cwd=repo_path,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True
                    )
                    
                    # Check if remote branch exists
                    remote_branches = subprocess.run(
                        ['git', 'branch', '-r', '--list', f'origin/{branch}'],
                        cwd=repo_path,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True
                    )
                    
                    has_local = local_branches.stdout.strip() != ''
                    has_remote = remote_branches.stdout.strip() != ''
                    
                    checkout_result = None
                    
                    if has_local:
                        # Branch exists locally, just checkout
                        checkout_result = subprocess.run(
                            ['git', 'checkout', branch],
                            cwd=repo_path,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True
                        )
                    elif has_remote:
                        # Branch exists remotely, create tracking branch
                        # Use --track to automatically set up tracking
                        checkout_result = subprocess.run(
                            ['git', 'checkout', '--track', f'origin/{branch}'],
                            cwd=repo_path,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True
                        )
                    else:
                        # Try direct checkout (might work if git can resolve it)
                        checkout_result = subprocess.run(
                            ['git', 'checkout', branch],
                            cwd=repo_path,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True
                        )
                        
                        if checkout_result.returncode != 0:
                            # Last resort: try to create branch from remote
                            checkout_result = subprocess.run(
                                ['git', 'checkout', '-b', branch, f'origin/{branch}'],
                                cwd=repo_path,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                text=True
                            )
                    
                    if checkout_result and checkout_result.returncode == 0:
                        print(f"Successfully checked out branch '{branch}'")
                    else:
                        # Check what branch we're actually on
                        current_result = subprocess.run(
                            ['git', 'branch', '--show-current'],
                            cwd=repo_path,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True
                        )
                        current_branch = current_result.stdout.strip() if current_result.returncode == 0 else "unknown"
                        print(f"Warning: Could not checkout branch '{branch}' (branch may not exist)", file=sys.stderr)
                        print(f"         Remaining on branch: {current_branch}", file=sys.stderr)
                        if checkout_result and checkout_result.stdout and checkout_result.stdout.strip():
                            # Only show error if there's actual output (avoid noise)
                            error_lines = checkout_result.stdout.strip().split('\n')
                            # Filter out common non-critical messages
                            important_errors = [line for line in error_lines 
                                              if 'fatal' in line.lower() or 'error' in line.lower()]
                            if important_errors:
                                print(f"         Git message: {important_errors[0]}", file=sys.stderr)
                except Exception as e:
                    print(f"Warning: Error while checking out branch '{branch}': {e}", file=sys.stderr)
                    print(f"         Installation will continue with default branch", file=sys.stderr)
        except subprocess.CalledProcessError as e:
            print(f"Error cloning repository: {e}", file=sys.stderr)
            if e.stderr:
                print(e.stderr.decode(), file=sys.stderr)
            return False
        
        # Check dependencies
        deps_satisfied = True
        if not skip_dependency_check:
            print("Checking dependencies...")
            deps_satisfied, missing_system, missing_gitpm, can_install_system, gitpm_dep_info, json_error = self.check_dependencies(repo_path)
            
            # Check for JSON errors
            if json_error:
                print(f"Error: {json_error}", file=sys.stderr)
                # Clean up cloned directory
                if cloned and repo_path.exists():
                    import shutil
                    try:
                        shutil.rmtree(repo_path)
                        print(f"Cleaned up cloned directory: {repo_path}", file=sys.stderr)
                    except Exception as e:
                        print(f"Warning: Could not clean up directory {repo_path}: {e}", file=sys.stderr)
                return False
        
        if not skip_dependency_check and not deps_satisfied:
            print("Missing dependencies detected:")
            if missing_system:
                print(f"  System packages: {', '.join(missing_system)}")
            if missing_gitpm:
                print(f"  GitPM packages: {', '.join(missing_gitpm)}")
            
            # Try to install system packages if possible
            if missing_system and can_install_system:
                gitpm_json = self.load_gitpm_json(repo_path)
                if gitpm_json and 'dependencies' in gitpm_json and 'system' in gitpm_json['dependencies']:
                    system_deps = gitpm_json['dependencies']['system']
                    # Get install method
                    install_method = system_deps.get('method', '')
                    if not install_method:
                        install_method = system_deps.get(f'{self.distro}_method', '')
                    
                    if install_method:
                        print(f"\nAttempting to install missing system packages...")
                        if self.install_system_packages(missing_system, system_deps, install_method):
                            # Re-check dependencies
                            deps_satisfied, missing_system, missing_gitpm, _, _, _ = self.check_dependencies(repo_path)
                        else:
                            print("Failed to install system packages. Please install them manually.", file=sys.stderr)
            
            # Install gitpm dependencies
            if missing_gitpm and gitpm_dep_info:
                print(f"\nInstalling missing GitPM dependencies: {', '.join(missing_gitpm)}")
                for dep in gitpm_dep_info:
                    dep_name = dep['name']
                    dep_url = dep['url']
                    
                    # Check if dependency requires system install
                    # We need to check the dependency's gitpm.json before installing
                    # Do a quick compatibility check to get the gitpm.json
                    is_compatible, compat_msg = self.check_repo_compatibility(dep_url, dep.get('branch'))
                    if is_compatible:
                        # Create temp clone to check system_only
                        import tempfile
                        import shutil
                        temp_dir = tempfile.mkdtemp(prefix='gitpm_check_dep_')
                        temp_repo_path = Path(temp_dir) / "repo"
                        try:
                            clone_cmd = ['git', 'clone', '--depth', '1', '--no-checkout', dep_url, str(temp_repo_path)]
                            if dep.get('branch'):
                                clone_cmd.extend(['--branch', dep['branch']])
                            subprocess.run(clone_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
                            subprocess.run(['git', 'checkout', 'HEAD', '--'], cwd=temp_repo_path, 
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
                            
                            dep_json, _ = self.load_gitpm_json(temp_repo_path)
                            if dep_json and dep_json.get('system_only', False) and not self.system:
                                print(f"Error: Dependency '{dep_name}' requires system-wide installation", file=sys.stderr)
                                print(f"Please install this package with --system flag, or install '{dep_name}' as system first", file=sys.stderr)
                                # Clean up
                                shutil.rmtree(temp_dir, ignore_errors=True)
                                if cloned and repo_path.exists():
                                    shutil.rmtree(repo_path, ignore_errors=True)
                                    print(f"Cleaned up cloned directory: {repo_path}", file=sys.stderr)
                                return False
                        finally:
                            shutil.rmtree(temp_dir, ignore_errors=True)
                    
                    print(f"Installing dependency: {dep_name}")
                    # Install with skip_dependency_check to avoid infinite recursion
                    # If dependency requires system, install it as system
                    dep_system = self.system  # Use same install type as parent
                    if not dep_system:
                        # Check if we need to install as system
                        # (We already checked above, but double-check)
                        pass
                    
                    # For now, install with same system flag as parent
                    # In the future, we could auto-detect and switch
                    if not self.install(dep_name, skip_compatibility_check=False, skip_dependency_check=True):
                        print(f"Error: Failed to install dependency '{dep_name}'", file=sys.stderr)
                        # Clean up cloned directory
                        if cloned and repo_path.exists():
                            import shutil
                            try:
                                shutil.rmtree(repo_path)
                                print(f"Cleaned up cloned directory: {repo_path}", file=sys.stderr)
                            except Exception as e:
                                print(f"Warning: Could not clean up directory {repo_path}: {e}", file=sys.stderr)
                        return False
                # Re-check after installing gitpm deps
                deps_satisfied, missing_system, missing_gitpm, _, _, _ = self.check_dependencies(repo_path)
            
            if not deps_satisfied:
                if missing_system and not can_install_system:
                    print("\nError: Missing system packages and cannot install them (no sudo access)", file=sys.stderr)
                    print("Please install the following packages manually:", file=sys.stderr)
                    for pkg in missing_system:
                        print(f"  - {pkg}", file=sys.stderr)
                    # Clean up cloned directory
                    if cloned and repo_path.exists():
                        import shutil
                        try:
                            shutil.rmtree(repo_path)
                            print(f"Cleaned up cloned directory: {repo_path}", file=sys.stderr)
                        except Exception as e:
                            print(f"Warning: Could not clean up directory {repo_path}: {e}", file=sys.stderr)
                    return False
                elif missing_system:
                    print("\nError: Some system packages could not be installed", file=sys.stderr)
                    # Clean up cloned directory
                    if cloned and repo_path.exists():
                        import shutil
                        try:
                            shutil.rmtree(repo_path)
                            print(f"Cleaned up cloned directory: {repo_path}", file=sys.stderr)
                        except Exception as e:
                            print(f"Warning: Could not clean up directory {repo_path}: {e}", file=sys.stderr)
                    return False
        
        if not skip_dependency_check:
            print("All dependencies satisfied")
        
        # Check for setup script
        scripts = self.check_scripts(repo_path)
        
        # Run setup script if found
        if scripts['setup']:
            print(f"Running setup script: {scripts['setup']}")
            if not self.run_script(scripts['setup'], repo_path):
                print("Warning: Setup script failed, but repository was cloned.")
        
        # Register installation
        self.installed[install_name] = {
            'url': repo_url,
            'user': user,
            'name': install_name,
            'repo_name': repo_name,
            'branch': branch,
            'path': str(repo_path),
            'setup_script': str(scripts['setup']) if scripts['setup'] else None,
            'remove_script': str(scripts['remove']) if scripts['remove'] else None,
            'update_script': str(scripts['update']) if scripts['update'] else None,
            'check_script': str(scripts['check']) if scripts['check'] else None
        }
        self.save_installed()
        
        branch_info = f" (branch: {branch})" if branch else ""
        print(f"Successfully installed '{install_name}'{branch_info}")
        return True
    
    def update(self, name: Optional[str] = None, check_only: bool = False) -> bool:
        """Update installed packages
        If check_only is True, only checks for updates without applying them
        """
        if name:
            # Update specific package
            if name not in self.installed:
                print(f"Error: '{name}' is not installed")
                return False
            
            repo_info = self.installed[name]
            repo_path = Path(repo_info['path'])
            if not repo_path.exists():
                print(f"Error: Installation path {repo_path} does not exist")
                return False
            
            branch = repo_info.get('branch')
            
            if check_only:
                print(f"Checking for updates: {name}...")
            else:
                print(f"Updating {name}...")
            
            try:
                # Fetch latest changes
                subprocess.run(
                    ['git', 'fetch', 'origin'],
                    cwd=repo_path,
                    check=True,
                    capture_output=True
                )
                
                # Check if there are updates available
                current_commit = subprocess.run(
                    ['git', 'rev-parse', 'HEAD'],
                    cwd=repo_path,
                    capture_output=True,
                    text=True
                ).stdout.strip()
                
                # Get remote commit for branch
                remote_ref = f'origin/{branch}' if branch else 'origin/HEAD'
                remote_commit = subprocess.run(
                    ['git', 'rev-parse', remote_ref],
                    cwd=repo_path,
                    capture_output=True,
                    text=True
                ).stdout.strip()
                
                # Check for check script first
                scripts = self.check_scripts(repo_path)
                has_check_script = scripts['check'] is not None
                updates_available = False
                
                if has_check_script:
                    # Run check script to determine if updates are available
                    print(f"Running check script: {scripts['check']}")
                    check_exit_code = self.run_script(scripts['check'], repo_path, return_exit_code=True)
                    
                    # Exit code 1 means updates available (0 = no updates, other = error)
                    if check_exit_code == 1:
                        updates_available = True
                    elif check_exit_code == 0:
                        updates_available = False
                    else:
                        print(f"Warning: Check script returned error code {check_exit_code}", file=sys.stderr)
                        # Fall back to git commit comparison on error
                        updates_available = (current_commit != remote_commit)
                else:
                    # No check script, use git commit comparison
                    updates_available = (current_commit != remote_commit)
                
                if not updates_available:
                    print(f"'{name}' is already up to date")
                    return True
                
                if check_only:
                    print(f"Update available for '{name}'")
                    return True
                
                # Checkout the correct branch if specified
                if branch:
                    subprocess.run(
                        ['git', 'checkout', branch],
                        cwd=repo_path,
                        check=True,
                        capture_output=True
                    )
                
                # Pull latest changes
                subprocess.run(
                    ['git', 'pull'],
                    cwd=repo_path,
                    check=True
                )
                
                # Check for update script first, then fall back to setup script
                scripts = self.check_scripts(repo_path)
                if scripts['update']:
                    print(f"Running update script: {scripts['update']}")
                    if not self.run_script(scripts['update'], repo_path):
                        print("Warning: Update script failed, but repository was updated.")
                elif scripts['setup']:
                    print(f"Re-running setup script: {scripts['setup']}")
                    self.run_script(scripts['setup'], repo_path)
                
                # Update stored script paths if they changed
                if scripts['update']:
                    self.installed[name]['update_script'] = str(scripts['update'])
                if scripts['check']:
                    self.installed[name]['check_script'] = str(scripts['check'])
                if scripts['update'] or scripts['check']:
                    self.save_installed()
                
                branch_info = f" (branch: {branch})" if branch else ""
                print(f"Successfully updated '{name}'{branch_info}")
                return True
            except subprocess.CalledProcessError as e:
                print(f"Error updating '{name}': {e}", file=sys.stderr)
                return False
        else:
            # Update all packages
            if not self.installed:
                print("No packages installed.")
                return True
            
            print(f"Updating {len(self.installed)} package(s)...")
            success = True
            for name in list(self.installed.keys()):
                if not self.update(name):
                    success = False
            
            return success
    
    def remove(self, name: str, skip_uninstall: bool = False) -> bool:
        """Remove an installed package"""
        if name not in self.installed:
            print(f"Error: '{name}' is not installed")
            return False
        
        repo_info = self.installed[name]
        repo_path = Path(repo_info['path'])
        
        if not repo_path.exists():
            print(f"Warning: Installation path {repo_path} does not exist")
            # Remove from registry anyway
            del self.installed[name]
            self.save_installed()
            return True
        
        # Run removal script if found and not skipping
        if not skip_uninstall:
            scripts = self.check_scripts(repo_path)
            remove_script = scripts['remove'] or scripts['uninstall']
            
            if remove_script:
                print(f"Running removal script: {remove_script}")
                self.run_script(remove_script, repo_path)
            elif repo_info.get('remove_script'):
                # Use stored script path
                remove_script = Path(repo_info['remove_script'])
                if remove_script.exists():
                    print(f"Running removal script: {remove_script}")
                    self.run_script(remove_script, repo_path)
        
        # Remove directory
        try:
            import shutil
            shutil.rmtree(repo_path)
            print(f"Removed {repo_path}")
        except Exception as e:
            print(f"Error removing directory: {e}", file=sys.stderr)
            return False
        
        # Remove from registry
        del self.installed[name]
        self.save_installed()
        
        print(f"Successfully removed '{name}'")
        return True
    
    def list_installed(self):
        """List all installed packages"""
        if not self.installed:
            print("No packages installed.")
            return
        
        print(f"\nInstalled packages ({len(self.installed)}):")
        print("-" * 100)
        print(f"{'Name':<25} {'User':<20} {'Branch':<15} {'Path':<40}")
        print("-" * 100)
        
        for name, info in sorted(self.installed.items()):
            user = info.get('user', 'unknown')
            branch = info.get('branch', 'default')
            path = info.get('path', 'unknown')
            print(f"{name:<25} {user:<20} {branch:<15} {path:<40}")
    
    def list_available(self, search: Optional[str] = None, show_source: bool = False):
        """List all available packages from config"""
        repos = self.load_config()
        
        if not repos:
            print("No repositories in config file(s).")
            return
        
        # Parse all repos
        repo_list = []
        for repo_entry in repos:
            repo_url = repo_entry['url']
            _, user, repo_name = self.parse_repo_url(repo_url)
            display_name = repo_entry['name'] if repo_entry['name'] else repo_name
            branch = repo_entry['branch'] or 'default'
            
            repo_list.append({
                'name': display_name,
                'repo_name': repo_name,
                'user': user,
                'url': repo_url,
                'branch': branch,
                'installed': display_name in self.installed,
                'source_file': repo_entry.get('source_file', 'unknown')
            })
        
        # Filter by search if provided
        if search:
            search_lower = search.lower()
            repo_list = [
                r for r in repo_list
                if search_lower in r['name'].lower() or 
                   search_lower in r['user'].lower() or
                   search_lower in r['repo_name'].lower() or
                   search_lower in r.get('source_file', '').lower()
            ]
        
        # Sort and display
        repo_list.sort(key=lambda x: x['name'])
        
        print(f"\nAvailable packages ({len(repo_list)}):")
        if show_source:
            print("-" * 120)
            print(f"{'Name':<25} {'User':<20} {'Branch':<15} {'Status':<15} {'Source':<15} {'URL':<25}")
            print("-" * 120)
        else:
            print("-" * 100)
            print(f"{'Name':<25} {'User':<20} {'Branch':<15} {'Status':<15} {'URL':<25}")
            print("-" * 100)
        
        for repo in repo_list:
            status = "[INSTALLED]" if repo['installed'] else "[AVAILABLE]"
            name = repo['name']
            user = repo['user']
            branch = repo['branch']
            url = repo['url'][:23] + "..." if len(repo['url']) > 25 else repo['url']
            if show_source:
                source = repo.get('source_file', 'unknown')[:13] + "..." if len(repo.get('source_file', '')) > 15 else repo.get('source_file', 'unknown')
                print(f"{name:<25} {user:<20} {branch:<15} {status:<15} {source:<15} {url:<25}")
            else:
                print(f"{name:<25} {user:<20} {branch:<15} {status:<15} {url:<25}")


def main():
    parser = argparse.ArgumentParser(
        description='Git Package Manager - Install and manage applications from git repositories'
    )
    parser.add_argument(
        '--system',
        action='store_true',
        help='Install to system location (/opt/apps) instead of user location'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # install command
    install_parser = subparsers.add_parser('install', help='Install a package')
    install_parser.add_argument('name', help='Package name to install')
    install_parser.add_argument(
        '--force',
        action='store_true',
        help='Skip compatibility check and install anyway'
    )
    
    # update command
    update_parser = subparsers.add_parser('update', help='Update packages')
    update_parser.add_argument('name', nargs='?', help='Package name to update (optional, updates all if omitted)')
    update_parser.add_argument(
        '--check',
        action='store_true',
        help='Check for updates without applying them'
    )
    
    # remove command
    remove_parser = subparsers.add_parser('remove', help='Remove a package')
    remove_parser.add_argument('name', help='Package name to remove')
    
    # list command
    list_parser = subparsers.add_parser('list', help='List packages')
    list_parser.add_argument(
        '--installed',
        action='store_true',
        help='List only installed packages'
    )
    list_parser.add_argument(
        '--available',
        action='store_true',
        help='List only available packages from config'
    )
    list_parser.add_argument(
        '-s', '--search',
        help='Search for packages'
    )
    list_parser.add_argument(
        '--show-source',
        action='store_true',
        help='Show which config file each package comes from'
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Check for system flag permission
    if args.system and os.geteuid() != 0:
        print("Error: --system flag requires root privileges", file=sys.stderr)
        sys.exit(1)
    
    gpm = GitPackageManager(system=args.system)
    
    if args.command == 'install':
        success = gpm.install(args.name, skip_compatibility_check=args.force)
        sys.exit(0 if success else 1)
    
    elif args.command == 'update':
        success = gpm.update(args.name, check_only=args.check)
        sys.exit(0 if success else 1)
    
    elif args.command == 'remove':
        success = gpm.remove(args.name)
        sys.exit(0 if success else 1)
    
    elif args.command == 'list':
        if args.installed:
            gpm.list_installed()
        elif args.available:
            gpm.list_available(search=args.search, show_source=args.show_source)
        else:
            # Show both
            gpm.list_installed()
            print()
            gpm.list_available(search=args.search, show_source=args.show_source)
    
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

