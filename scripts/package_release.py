"""Create a source handoff without environment files or local runtime data."""
import argparse
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from drugagent import __version__

ROOT_FILES = (
    'README.md', 'LICENSE', 'Dockerfile', 'compose.yaml', '.dockerignore', '.env.example',
    'requirements.txt', 'requirements.lock', 'requirements-dev.txt', 'agents.py', 'config.py',
    'llm.py', 'web.py', 'run.py', 'check_env.py', 'start.bat',
    'data/corpus.json', 'data/egfr_candidates.csv', 'docs/deployment.md', 'docs/LOCAL_AGENT_HANDOFF.md',
    'docs/example_report_EGFR.md',
)
CODE_DIRECTORIES = ('drugagent', 'tools', 'web', 'scripts', 'tests')
CODE_SUFFIXES = {'.py', '.js', '.cjs', '.css', '.html', '.sh'}


def release_files():
    files = {ROOT / name for name in ROOT_FILES}
    for name in CODE_DIRECTORIES:
        files.update(path for path in (ROOT / name).rglob('*')
                     if path.is_file() and not path.is_symlink() and path.suffix in CODE_SUFFIXES
                     and '__pycache__' not in path.parts and 'node_modules' not in path.parts)
    for path in sorted(files):
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(f'Required release file unavailable: {path.relative_to(ROOT)}')
        yield path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path,
                        default=ROOT / 'dist' / f'DrugAgent-v{__version__}.zip')
    destination = parser.parse_args(argv).output.resolve()
    files = list(release_files())
    if destination in files:
        raise ValueError('Output cannot replace a source file')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, 'w', compression=ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, str(Path('drugagent') / path.relative_to(ROOT)))
    print(f'Created {destination} ({len(files)} files)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
