"""Install the checksum-pinned Apple Silicon compiler into the local workspace."""
import hashlib
import json
import platform
import subprocess
import tarfile
import tempfile
from pathlib import Path

from .common import ROOT, require


def ensure():
    require(platform.system() == 'Darwin' and platform.machine() == 'arm64',
            'Automatic setup supports Apple Silicon macOS. Other hosts need an explicit GCC_PATH.')
    config = json.loads((ROOT / 'config/mario-toolchain.json').read_text())
    cache = ROOT / '.local/toolchains'
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / config['archive']
    if not archive.exists():
        with tempfile.TemporaryDirectory(prefix='download-', dir=cache) as tmp:
            pending = Path(tmp) / config['archive']
            subprocess.run(['curl', '--fail', '--location', '--retry', '3',
                            '--connect-timeout', '30', '--max-time', '900',
                            '--output', str(pending), config['url']], check=True)
            with pending.open('rb') as stream:
                require(hashlib.file_digest(stream, 'sha256').hexdigest() == config['archive_sha256'],
                        'Downloaded toolchain archive hash mismatch')
            pending.rename(archive)
    with archive.open('rb') as stream:
        require(hashlib.file_digest(stream, 'sha256').hexdigest() == config['archive_sha256'],
                'Toolchain archive hash mismatch')
    compiler = cache / config['compiler_subdirectory'] / 'arm-none-eabi-gcc'
    if not compiler.exists():
        target = (cache / config['compiler_subdirectory']).parent
        require(not target.exists(), 'Incomplete toolchain directory exists; move it aside and retry')
        with tempfile.TemporaryDirectory(prefix='extract-', dir=cache) as tmp:
            with tarfile.open(archive) as bundle:
                bundle.extractall(tmp, filter='data')
            staged = Path(tmp) / target.name
            require((staged / 'bin/arm-none-eabi-gcc').is_file(), 'Archive has no expected compiler')
            staged.rename(target)
    version = subprocess.check_output([str(compiler), '-dumpfullversion'], text=True).strip()
    require(version == config['compiler_version'], 'Compiler version differs from pinned version')
    return compiler.parent


if __name__ == '__main__':
    print(ensure())
