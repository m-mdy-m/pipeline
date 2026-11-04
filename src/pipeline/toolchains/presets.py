"""Per-language defaults for the shared CI stages.

Every preset is a pure function of the project's files. Nothing here knows
about GitHub, GitLab or any other provider: providers only install the runtime
(Node, Go, Rust, ...) and then call ``pipeline ci``.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

# Execution order. ``test`` is the only stage a project must always provide.
STAGES = ("install", "configure", "lint", "build", "test")
REQUIRED_STAGES = ("test",)


@dataclass(frozen=True)
class Step:
    """One command belonging to a stage."""

    stage: str
    command: tuple[str, ...]
    description: str = ""
    env: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Preset:
    name: str
    description: str
    markers: tuple[str, ...]
    steps: Callable[[Path, Mapping[str, str]], list[Step]]
    # Executables the provider must put on PATH before ``pipeline ci`` runs.
    runtime: tuple[str, ...] = ()
    # Stages that must produce a command; a build-only artifact (a container image) needs none.
    required: tuple[str, ...] = REQUIRED_STAGES


def _has(root: Path, *names: str) -> bool:
    return any(any(root.glob(name)) if "*" in name else (root / name).exists() for name in names)


def _on(options: Mapping[str, str], key: str, default: bool = False) -> bool:
    value = options.get(key)
    if value is None or value == "":
        return default
    if value.lower() in ("1", "true", "yes", "on"):
        return True
    if value.lower() in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"option {key} must be true or false, not {value!r}")


def _check(name: str, *args: str) -> tuple[str, ...]:
    return ("python", "-m", "pipeline.toolchains.checks", name, *args)


def _make_has_target(root: Path, target: str) -> bool:
    for name in ("Makefile", "makefile", "GNUmakefile"):
        path = root / name
        if path.is_file():
            return bool(re.search(rf"(?m)^{re.escape(target)}\s*:", path.read_text(encoding="utf-8", errors="replace")))
    return False


def _package_json(root: Path) -> dict:
    try:
        data = json.loads((root / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


# --------------------------------------------------------------------- python
def _python(root: Path, options: Mapping[str, str]) -> list[Step]:
    steps: list[Step] = []
    if (root / "requirements.txt").is_file():
        steps.append(Step("install", ("python", "-m", "pip", "install", "-r", "requirements.txt")))
    elif (root / "pyproject.toml").is_file() or (root / "setup.py").is_file():
        steps.append(Step("install", ("python", "-m", "pip", "install", "-e", ".")))
    source = options.get("source") or next((d for d in ("src", "app") if (root / d).is_dir()), "")
    if source:
        if not (root / source).is_dir():
            raise ValueError(f"source directory does not exist: {source}")
        steps.append(Step("build", ("python", "-m", "compileall", "-q", source), "Byte-compile the sources"))
    tests = options.get("tests", "tests")
    pattern = options.get("test_pattern", "test_*.py")
    runner = options.get("runner", "")
    if runner not in ("", "pytest", "unittest"):
        raise ValueError(f"runner must be pytest or unittest, not {runner!r}")
    pyproject = root / "pyproject.toml"
    pytest_configured = _has(root, "pytest.ini", "conftest.py", "tests/conftest.py") or (
        pyproject.is_file() and "[tool.pytest" in pyproject.read_text(encoding="utf-8")
    )
    env = (("PYTHONPATH", source),) if source else ()
    if runner == "pytest" or (not runner and pytest_configured):
        steps.append(Step("test", ("python", "-m", "pytest"), "Run pytest", env))
    elif (root / tests).is_dir():
        steps.append(Step("test", ("python", "-m", "unittest", "discover", "-s", tests, "-p", pattern, "-v"), "Run unittest", env))
    return steps


# --------------------------------------------------------------------- node
def node_package_manager(root: Path, options: Mapping[str, str] | None = None) -> str:
    chosen = (options or {}).get("package_manager", "")
    if chosen:
        if chosen not in ("npm", "pnpm", "yarn", "bun"):
            raise ValueError(f"package_manager must be npm, pnpm, yarn or bun, not {chosen!r}")
        return chosen
    if _has(root, "pnpm-lock.yaml"):
        return "pnpm"
    if _has(root, "bun.lock", "bun.lockb"):
        return "bun"
    if _has(root, "yarn.lock"):
        return "yarn"
    return "npm"


_NO_TEST = re.compile(r"no test specified", re.IGNORECASE)


def _node(root: Path, options: Mapping[str, str]) -> list[Step]:
    manager = node_package_manager(root, options)
    scripts = _package_json(root).get("scripts") or {}
    if manager == "npm":
        locked = _has(root, "package-lock.json", "npm-shrinkwrap.json")
        install = ("npm", "ci") if locked else ("npm", "install")
    elif manager == "pnpm":
        install = ("pnpm", "install", "--frozen-lockfile")
    elif manager == "bun":
        install = ("bun", "install", "--frozen-lockfile")
    else:  # yarn classic vs. berry
        berry = _has(root, ".yarnrc.yml")
        install = ("yarn", "install", "--immutable" if berry else "--frozen-lockfile")
    steps = [Step("install", install, f"Install dependencies with {manager}")]

    def script(stage: str, name: str) -> None:
        body = scripts.get(name)
        if isinstance(body, str) and body.strip() and not (name == "test" and _NO_TEST.search(body)):
            steps.append(Step(stage, (manager, "run", name), f"{manager} run {name}"))

    for lint_script in ("format:check", "lint", "typecheck"):
        script("lint", lint_script)
    script("build", "build")
    script("test", "test")
    return steps


# --------------------------------------------------------------------- go
def _go(root: Path, options: Mapping[str, str]) -> list[Step]:
    steps = [Step("install", ("go", "mod", "download"), "Download modules")]
    if _on(options, "gofmt", True):
        steps.append(Step("lint", _check("gofmt"), "gofmt must list no files"))
    steps.append(Step("lint", ("go", "vet", "./..."), "go vet"))
    if _on(options, "tidy"):
        steps.append(Step("lint", _check("go-mod-tidy"), "go.mod and go.sum are tidy"))
    if _on(options, "golangci"):
        steps.append(Step("lint", ("golangci-lint", "run"), "golangci-lint"))
    test = ["go", "test"]
    if _on(options, "race"):
        test.append("-race")
    if _on(options, "cover"):
        test.append("-cover")
    return steps + [
        Step("build", ("go", "build", "./..."), "go build"),
        Step("test", (*test, "./..."), "go test"),
    ]


# --------------------------------------------------------------------- rust
def _rust(root: Path, options: Mapping[str, str]) -> list[Step]:
    fetch = ("cargo", "fetch", "--locked") if (root / "Cargo.lock").is_file() else ("cargo", "fetch")
    locked = ("--locked",) if (root / "Cargo.lock").is_file() else ()
    return [
        Step("install", fetch, "Fetch crates"),
        Step("lint", ("cargo", "clippy", "--all-targets", *locked, "--", "-D", "warnings"), "clippy"),
        Step("build", ("cargo", "build", *locked), "cargo build"),
        Step("test", ("cargo", "test", *locked), "cargo test"),
    ]


# --------------------------------------------------------------------- java
def _java(root: Path, options: Mapping[str, str]) -> list[Step]:
    tool = options.get("build_tool", "")
    if tool not in ("", "maven", "gradle"):
        raise ValueError(f"build_tool must be maven or gradle, not {tool!r}")
    if tool == "maven" or (not tool and (root / "pom.xml").is_file()):
        mvn = ("./mvnw",) if (root / "mvnw").is_file() else ("mvn",)
        flags = ("-B", "-ntp")
        return [
            Step("build", (*mvn, *flags, "-DskipTests", "package"), "Maven package without tests"),
            Step("test", (*mvn, *flags, "verify"), "Maven verify"),
        ]
    gradle = ("./gradlew",) if (root / "gradlew").is_file() else ("gradle",)
    return [
        Step("build", (*gradle, "--no-daemon", "assemble"), "Gradle assemble"),
        Step("test", (*gradle, "--no-daemon", "check"), "Gradle check"),
    ]


# --------------------------------------------------------------------- dotnet
def _dotnet(root: Path, options: Mapping[str, str]) -> list[Step]:
    return [
        Step("install", ("dotnet", "restore"), "Restore packages"),
        Step("build", ("dotnet", "build", "--no-restore", "-c", "Release"), "dotnet build"),
        Step("test", ("dotnet", "test", "--no-build", "-c", "Release"), "dotnet test"),
    ]


# --------------------------------------------------------------------- c / c++
def _c(root: Path, options: Mapping[str, str]) -> list[Step]:
    if (root / "CMakeLists.txt").is_file():
        configure = ["cmake", "-S", ".", "-B", "build"]
        if options.get("generator"):
            configure += ["-G", options["generator"]]
        if options.get("build_type"):
            configure.append(f"-DCMAKE_BUILD_TYPE={options['build_type']}")
        if options.get("sanitize"):
            flags = f"-fsanitize={options['sanitize']} -fno-omit-frame-pointer"
            configure += [f"-DCMAKE_C_FLAGS={flags}", f"-DCMAKE_CXX_FLAGS={flags}", f"-DCMAKE_EXE_LINKER_FLAGS=-fsanitize={options['sanitize']}"]
        return [
            Step("configure", tuple(configure), "Configure CMake"),
            Step("build", ("cmake", "--build", "build"), "Build"),
            Step("test", ("ctest", "--test-dir", "build", "--output-on-failure"), "ctest"),
        ]
    steps = [Step("build", ("make",), "make")]
    if _make_has_target(root, "check"):
        steps.append(Step("test", ("make", "check"), "make check"))
    elif _make_has_target(root, "test"):
        steps.append(Step("test", ("make", "test"), "make test"))
    return steps


# --------------------------------------------------------------------- vim
def _vim(root: Path, options: Mapping[str, str]) -> list[Step]:
    vim = options.get("vim", "vim")
    steps = [Step("lint", _check("vim-features", vim), "Vim has +job and +timers")]
    if any((root / "plugin").glob("*.vim")):
        steps.append(Step("lint", _check("vim-load", vim), "plugins load without errors"))
    if (root / "doc").is_dir():
        steps.append(Step("lint", _check("vim-helptags", vim), "helptags can be generated"))
    if _make_has_target(root, "test"):
        steps.append(Step("test", ("make", "test"), "make test"))
    return steps


# --------------------------------------------------------------------- latex
def _latex(root: Path, options: Mapping[str, str]) -> list[Step]:
    """Build a LaTeX project and verify that at least one valid PDF was produced."""
    engine = options.get("engine", "pdflatex").lower()
    engines = {
        "pdflatex": "-pdf",
        "xelatex": "-xelatex",
        "lualatex": "-lualatex",
    }
    if engine not in engines:
        raise ValueError(f"engine must be pdflatex, xelatex or lualatex, not {engine!r}")

    output = options.get("output", "build")
    output_path = Path(output)
    if output_path.is_absolute() or ".." in output_path.parts or not output:
        raise ValueError("output must be a non-empty path inside the project")

    source = options.get("source", "")
    if _make_has_target(root, "build"):
        build = Step("build", ("make", "build"), "Run the project's configured LaTeX build")
    else:
        if not source:
            candidates = sorted(path.name for path in root.glob("*.tex") if path.is_file())
            if (root / "main.tex").is_file():
                source = "main.tex"
            elif len(candidates) == 1:
                source = candidates[0]
            elif not candidates:
                raise ValueError("no root-level .tex source found; set source=... or add a Makefile build target")
            else:
                raise ValueError("multiple .tex sources found; set source=... or add a Makefile build target")
        source_path = Path(source)
        if source_path.is_absolute() or ".." in source_path.parts or source_path.suffix.lower() != ".tex":
            raise ValueError("source must be a .tex path inside the project")
        if not (root / source_path).is_file():
            raise ValueError(f"LaTeX source does not exist: {source}")
        command = (
            "latexmk", engines[engine], "-interaction=nonstopmode", "-halt-on-error",
            "-file-line-error", f"-outdir={output}", source,
        )
        build = Step("build", command, f"Build {source} with {engine}")

    return [
        build,
        Step("test", _check("latex-pdf", output), "Validate generated PDF files"),
    ]


# --------------------------------------------------------------------- docker
def _docker(root: Path, options: Mapping[str, str]) -> list[Step]:
    return [Step("build", ("docker", "build", "-f", "Dockerfile", "-t", "pipeline-ci:local", "."), "Build the image")]


PRESETS: dict[str, Preset] = {p.name: p for p in (
    Preset("go", "Go modules", ("go.mod",), _go, ("go",)),
    Preset("rust", "Rust (Cargo)", ("Cargo.toml",), _rust, ("cargo",)),
    Preset("java", "Java (Maven or Gradle)", ("pom.xml", "build.gradle", "build.gradle.kts"), _java, ("java",)),
    Preset("dotnet", ".NET", ("*.sln", "*.csproj", "*.fsproj"), _dotnet, ("dotnet",)),
    Preset("node", "Node.js (npm, pnpm, yarn, bun)", ("package.json",), _node, ("node",)),
    Preset("python", "Python", ("pyproject.toml", "setup.py", "requirements.txt"), _python, ("python",)),
    Preset("vim", "Vim/Neovim plugin", ("plugin/*.vim", "autoload/*.vim"), _vim, ("vim",)),
    Preset("latex", "LaTeX documents (pdfLaTeX, XeLaTeX or LuaLaTeX)", ("main.tex", "latexmkrc", ".latexmkrc", "*.tex"), _latex, ("latexmk",), ("build", "test")),
    Preset("c", "C/C++ (CMake or Make)", ("CMakeLists.txt", "Makefile", "makefile", "GNUmakefile"), _c, ()),
    Preset("docker", "Container image (Dockerfile)", ("Dockerfile",), _docker, ("docker",), ()),
)}


def available_languages() -> list[str]:
    return sorted(PRESETS)


def matches(root: Path, preset: Preset) -> bool:
    return _has(root, *preset.markers)
