"""Portable repository checks that presets call as ``python -m pipeline.toolchains.checks NAME``.

Each check is plain Python so it behaves identically on every provider and on a
developer machine; none of them knows which CI service started it.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence

_SKIP_DIRS = ("vendor/", "build/", "node_modules/")


def _run(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(list(command), cwd=cwd, capture_output=True, text=True, check=False)
    except OSError as exc:
        print(f"cannot run {command[0]}: {exc}", file=sys.stderr)
        raise SystemExit(127) from exc


def gofmt(root: Path, paths: Sequence[str]) -> int:
    """Fail when ``gofmt -l`` lists any file (vendored and build output are ignored)."""
    done = _run(["gofmt", "-l", *(paths or ["."])], root)
    if done.returncode != 0:
        print(done.stderr, file=sys.stderr, end="")
        return done.returncode
    files = [line for line in done.stdout.splitlines() if line and not line.replace("\\", "/").startswith(_SKIP_DIRS)]
    if files:
        print("These files need gofmt:", file=sys.stderr)
        for name in files:
            print(f"  {name}", file=sys.stderr)
        return 1
    return 0


def go_mod_tidy(root: Path, paths: Sequence[str]) -> int:
    """Fail when ``go mod tidy`` would change go.mod or go.sum; the originals are restored."""
    tracked = [root / "go.mod", root / "go.sum"]
    before = {p: p.read_bytes() for p in tracked if p.exists()}
    if root / "go.mod" not in before:
        print("go.mod not found", file=sys.stderr)
        return 2
    done = _run(["go", "mod", "tidy"], root)
    if done.returncode != 0:
        print(done.stderr, file=sys.stderr, end="")
        return done.returncode
    changed = [p.name for p in tracked if (p.read_bytes() if p.exists() else b"") != before.get(p, b"")]
    for path, data in before.items():
        path.write_bytes(data)
    for path in tracked:
        if path not in before and path.exists():
            path.unlink()
    if changed:
        print(f"{', '.join(changed)} is out of date; run 'go mod tidy' and commit the result", file=sys.stderr)
        return 1
    return 0


def vim_features(root: Path, paths: Sequence[str]) -> int:
    """Fail unless Vim has the +job and +timers features that async plugins need."""
    vim = paths[0] if paths else "vim"
    expr = 'if !(has("job") && has("timers")) | cquit 1 | endif'
    done = _run([vim, "-u", "NONE", "-N", "-es", "-c", expr, "-c", "quit"], root)
    if done.returncode != 0:
        print(f"{vim} lacks +job or +timers", file=sys.stderr)
    return done.returncode


def vim_load(root: Path, paths: Sequence[str]) -> int:
    """Source every ``plugin/*.vim`` in a clean, non-compatible Vim; any error fails the check."""
    vim = paths[0] if paths else "vim"
    files = sorted((root / "plugin").glob("*.vim")) if (root / "plugin").is_dir() else []
    if not files:
        print("no plugin/*.vim files", file=sys.stderr)
        return 2
    status = 0
    for path in files:
        done = _run([vim, "-u", "NONE", "-N", "-es", "-c", f"set rtp^={root.as_posix()}", "-c", f"runtime plugin/{path.name}", "-c", "quit"], root)
        if done.returncode != 0:
            print(f"{path.relative_to(root)} raised an error when loaded", file=sys.stderr)
            status = 1
    return status


def vim_helptags(root: Path, paths: Sequence[str]) -> int:
    """Fail when ``:helptags`` cannot be generated for the plugin's doc directory."""
    vim = paths[0] if paths else "vim"
    doc = root / "doc"
    if not doc.is_dir():
        print("no doc/ directory", file=sys.stderr)
        return 2
    existed = (doc / "tags").exists()
    done = _run([vim, "-u", "NONE", "-N", "-es", "-c", "helptags doc", "-c", "quit"], root)
    produced = (doc / "tags").is_file()
    if not existed and produced:
        (doc / "tags").unlink()
    if done.returncode != 0 or not produced:
        print("helptags generation failed", file=sys.stderr)
        return done.returncode or 1
    return 0


CHECKS: dict[str, Callable[[Path, Sequence[str]], int]] = {
    "gofmt": gofmt,
    "go-mod-tidy": go_mod_tidy,
    "vim-features": vim_features,
    "vim-load": vim_load,
    "vim-helptags": vim_helptags,
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.toolchains.checks", description=__doc__)
    parser.add_argument("name", choices=sorted(CHECKS))
    parser.add_argument("--root", default=".")
    parser.add_argument("args", nargs="*", help="check specific arguments (paths, executable)")
    ns = parser.parse_args(argv)
    return CHECKS[ns.name](Path(ns.root).resolve(), ns.args)


if __name__ == "__main__":
    raise SystemExit(main())
