from __future__ import annotations
import os
import posixpath
import re
import stat
import zipfile
from collections import Counter
from pathlib import Path
from .errors import ReleaseError
from .paths import safe_repo_path
from .tools import sha256_file


def zip_add_file(archive: zipfile.ZipFile, source: Path, archive_name: str) -> None:
    info = zipfile.ZipInfo(archive_name, date_time=(1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.compress_type = zipfile.ZIP_DEFLATED
    if source.is_symlink():
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, os.readlink(source).encode("utf-8"))
    else:
        mode = 0o755 if os.stat(source, follow_symlinks=False).st_mode & stat.S_IXUSR else 0o644
        info.external_attr = (stat.S_IFREG | mode) << 16
        archive.writestr(info, source.read_bytes())


def validate_zip(archive_path: Path, root_folder: str, archive_name: str, expected_changelog: str | None, expected_members: set[str]) -> int:
    if not archive_path.is_file() or archive_path.stat().st_size == 0:
        raise ReleaseError("Source ZIP is missing or empty")
    with zipfile.ZipFile(archive_path, "r") as archive:
        names = [item.filename for item in archive.infolist()]
        counts = Counter(names)
        if len(names) != len(counts):
            duplicates = sorted(name for name, count in counts.items() if count > 1)
            raise ReleaseError("Duplicate ZIP member names: " + ", ".join(duplicates))
        casefold_counts = Counter(name.casefold() for name in names)
        if len(casefold_counts) != len(names):
            duplicates = sorted(name for name, count in casefold_counts.items() if count > 1)
            raise ReleaseError("Case-insensitive ZIP filename collisions: " + ", ".join(duplicates))
        if archive.testzip() is not None:
            raise ReleaseError(f"ZIP CRC validation failed at member: {archive.testzip()}")
        for item in archive.infolist():
            name = item.filename
            if name.startswith("/") or "\\" in name or any(part in {"", ".", ".."} for part in name.rstrip("/").split("/")):
                raise ReleaseError(f"Unsafe ZIP member path: {name!r}")
            if not name.startswith(root_folder + "/"):
                raise ReleaseError(f"ZIP member is outside expected root folder {root_folder}/: {name}")
            relative_name = name[len(root_folder) + 1:]
            safe_repo_path(relative_name)
            if any(part.lower() == ".git" for part in name.split("/")):
                raise ReleaseError(f".git metadata found in ZIP: {name}")
            mode = (item.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                target = archive.read(name).decode("utf-8", "strict")
                if target.startswith("/") or "\\" in target or re.match(r"^[A-Za-z]:", target):
                    raise ReleaseError(f"Unsafe symlink in ZIP: {name} -> {target}")
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
                if resolved == ".." or resolved.startswith("../") or resolved.startswith("/"):
                    raise ReleaseError(f"Symlink escapes archive root: {name} -> {target}")
                if resolved != root_folder and not resolved.startswith(root_folder + "/"):
                    raise ReleaseError(f"Symlink escapes the source root folder: {name} -> {target}")
        non_metadata = [name for name in names if not name.endswith("/")]
        if not non_metadata:
            raise ReleaseError("Source ZIP contains no files")
        if set(non_metadata) != expected_members:
            missing = sorted(expected_members - set(non_metadata))
            unexpected = sorted(set(non_metadata) - expected_members)
            raise ReleaseError(f"ZIP contents differ from the staged snapshot; missing={missing}, unexpected={unexpected}")
        if expected_changelog and expected_changelog not in {name[len(root_folder) + 1:] for name in non_metadata}:
            raise ReleaseError(f"Changelog path missing from ZIP despite archive policy: {expected_changelog}")
        return len(non_metadata)
