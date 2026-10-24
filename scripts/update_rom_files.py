"""Track ROM inputs by content; preserve the dependency mtime when unchanged."""
import hashlib
import json
import sys
from pathlib import Path


def update(destination, directories):
    records = []
    for directory in directories:
        for path in sorted(directory.rglob('*')):
            if not path.is_file() or path.name == '.DS_Store' or path.suffix in ('.o', '.img', '.pyc'):
                continue
            # The parser generates compressed copies when the raw input exists.
            if path.suffix in ('.lzma', '.lz4', '.deflate', '.cdk') and path.with_suffix('').exists():
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            records.append((path.as_posix(), digest))
    contents = json.dumps(sorted(records), ensure_ascii=True, indent=2) + '\n'
    if not destination.exists() or destination.read_text() != contents:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(contents)
        print('Updated ROM input hashes')
        return True
    return False


if __name__ == '__main__':
    if len(sys.argv) < 3:
        raise SystemExit('Usage: update_rom_files.py FILE DIRECTORY [DIRECTORY ...]')
    update(Path(sys.argv[1]), [Path(arg) for arg in sys.argv[2:]])
