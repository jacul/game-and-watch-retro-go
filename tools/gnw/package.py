"""Create a new local installation package from a completed build. No device access."""
import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from .common import require
from .elf import verify_images
from .install import INTERNAL, EXTERNAL


def create(build_dir, output):
    names = (INTERNAL, EXTERNAL, 'gw_retro_go.elf')
    data = {name: (build_dir / name).read_bytes() for name in names}
    require(all(data.values()), 'Build contains an empty firmware file')
    verify_images(build_dir / 'gw_retro_go.elf', data[INTERNAL], data[EXTERNAL])
    require(not output.exists(), 'Package directory already exists')
    info = {'schema_version': 2, 'source_commit': None, 'source_dirty': None,
            'sha256': {name: hashlib.sha256(contents).hexdigest() for name, contents in data.items()},
            'flashed': False}
    provenance = build_dir / 'source-info.json'
    if provenance.exists():
        source = json.loads(provenance.read_text())
        require(source['sha256'] == info['sha256'], 'Build provenance does not match firmware')
        for key in ('source_commit', 'source_dirty', 'compiler_version'):
            info[key] = source[key]
    output.parent.mkdir(parents=True, exist_ok=True)
    # Build the complete package first. Never replace a previous package.
    with tempfile.TemporaryDirectory(prefix='.gnw-package-', dir=output.parent) as tmp:
        stage = Path(tmp) / 'package'
        stage.mkdir()
        for name, contents in data.items():
            (stage / name).write_bytes(contents)
        (stage / 'build-info.json').write_text(json.dumps(info, indent=2) + '\n')
        # Exclusive mkdir also handles a competing package writer.
        output.mkdir()
        for path in stage.iterdir():
            shutil.copyfile(path, output / path.name)
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', type=Path, default=Path('build'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    create(args.build_dir, args.output)
    print('Created local installation package:', args.output)


if __name__ == '__main__':
    main()
