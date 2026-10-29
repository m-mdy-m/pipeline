from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class TreeEntry:
    mode: str
    kind: str
    sha: str
    path: str
    repo_dir: Path
