"""Atomic replacement for regenerable JSON caches."""
import json
from pathlib import Path
from tempfile import NamedTemporaryFile


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=1)
        temporary.replace(path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
