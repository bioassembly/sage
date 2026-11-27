"""Inspect and explicitly provision the language servers selected by a SAGE profile."""
import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request


def native_command(command):
    if command and command[0] == 'bash-language-server' and 'microsoft' in platform.release().lower():
        return [sys.executable, str(Path(__file__).with_name('wsl_bash.py').resolve()), *command[1:]]
    return command


def provision(names, catalog, prefix, install=False):
    target = prefix.expanduser().resolve()
    packages = []
    binaries = []
    missing = []
    for name in names:
        spec = catalog[name]
        executable = spec['command'][0]
        found = shutil.which(executable, path=os.pathsep.join([str(target / 'bin'), os.environ.get('PATH', '')]))
        print(f'{name:12} {found or "missing"}')
        if not found:
            missing.append(name)
        packages.extend(spec.get('npm', []))
        if 'release' in spec and not found:
            binaries.append(spec)
    if not install:
        return missing
    for spec in binaries:
        machine = platform.machine().lower()
        if platform.system() != 'Linux' or machine not in spec['linux']:
            raise ValueError(f'Install {spec["command"][0]} for {platform.system()} {machine} before provisioning')
    if packages:
        subprocess.run(['npm', 'install', '--global', '--prefix', str(target), *dict.fromkeys(packages)], check=True)
    for spec in binaries:
        asset, digest = spec['linux'][platform.machine().lower()]
        bindir = target / 'bin'
        bindir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=bindir) as directory:
            staged = Path(directory) / 'download'
            with urllib.request.urlopen(spec['release'] + asset, timeout=60) as source, staged.open('wb') as out:
                shutil.copyfileobj(source, out)
            with staged.open('rb') as source:
                if hashlib.file_digest(source, 'sha256').hexdigest() != digest:
                    raise ValueError(f'Checksum mismatch for {asset}')
            staged.chmod(0o755)
            # A concurrent install or personal binary wins the name.
            try:
                os.link(staged, bindir / spec['command'][0])
            except FileExistsError:
                pass
