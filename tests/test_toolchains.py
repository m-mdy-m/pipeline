"""Language presets: detection, planning, overrides and real execution of the fixtures."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FIXTURES = ROOT / "examples" / "toolchains"
sys.path.insert(0, str(SRC))

from pipeline.toolchains import CIPlanError, PRESETS, STAGES, available_languages, build_plan, detect_toolchains, plan_to_config  # noqa: E402


def commands(plan) -> dict[str, list[list[str]]]:
    result: dict[str, list[list[str]]] = {}
    for step in plan.steps:
        result.setdefault(step.stage, []).append(list(step.command))
    return result


def copy_fixture(name: str, target: Path) -> Path:
    destination = target / name
    shutil.copytree(FIXTURES / name, destination, ignore=shutil.ignore_patterns("target", "build", "node_modules", "__pycache__", "*.egg-info"))
    return destination


def run_engine(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    for key in [k for k in env if k.startswith("PIPELINE_")]:
        del env[key]
    return subprocess.run([sys.executable, "-m", "pipeline", *args], cwd=project, env=env, capture_output=True, text=True, check=False)


class DetectionTests(unittest.TestCase):
    EXPECTED = {
        "python": "python", "node": "node", "go": "go", "rust": "rust", "java-maven": "java",
        "dotnet": "dotnet", "c-make": "c", "c-cmake": "c", "docker": "docker", "vim": "vim",
    }

    def test_every_fixture_is_detected_as_its_language(self) -> None:
        for fixture, language in self.EXPECTED.items():
            with self.subTest(fixture=fixture):
                self.assertEqual(detect_toolchains(FIXTURES / fixture)[0], language)

    def test_fixture_set_covers_every_preset(self) -> None:
        self.assertEqual(set(self.EXPECTED.values()), set(PRESETS))
        self.assertEqual(available_languages(), sorted(PRESETS))

    def test_empty_directory_has_no_toolchain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(detect_toolchains(tmp), [])
            with self.assertRaises(CIPlanError):
                build_plan(tmp)


class PlanTests(unittest.TestCase):
    def test_go_plan(self) -> None:
        plan = commands(build_plan(FIXTURES / "go"))
        self.assertEqual(plan["test"], [["go", "test", "./..."]])
        self.assertEqual(plan["lint"], [["python", "-m", "pipeline.toolchains.checks", "gofmt"], ["go", "vet", "./..."]])
        self.assertEqual(plan["test"], [["go", "test", "./..."]])

    def test_go_options_enable_race_cover_tidy_and_golangci(self) -> None:
        plan = commands(build_plan(FIXTURES / "go", options={"race": "true", "cover": "true", "tidy": "true", "golangci": "true", "gofmt": "false"}))
        self.assertEqual(plan["test"], [["go", "test", "-race", "-cover", "./..."]])
        self.assertEqual([c[0] for c in plan["lint"]], ["go", "python", "golangci-lint"])
        with self.assertRaises(CIPlanError):
            build_plan(FIXTURES / "go", options={"race": "maybe"})

    def test_vim_plugin_plan(self) -> None:
        plan = commands(build_plan(FIXTURES / "vim"))
        self.assertEqual(plan["test"], [["make", "test"]])
        self.assertEqual(len(plan["lint"]), 3)

    def test_make_check_target_is_preferred_and_cmake_options_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "Makefile").write_text("all:\n\ttrue\ncheck:\n\ttrue\ntest:\n\ttrue\n", encoding="utf-8")
            self.assertEqual(commands(build_plan(tmp))["test"], [["make", "check"]])
        cmake = commands(build_plan(FIXTURES / "c-cmake", options={"sanitize": "address,undefined", "generator": "Ninja", "build_type": "Debug"}))["configure"][0]
        self.assertIn("Ninja", cmake)
        self.assertIn("-DCMAKE_BUILD_TYPE=Debug", cmake)
        self.assertTrue(any(a.startswith("-DCMAKE_C_FLAGS=-fsanitize=address,undefined") for a in cmake))

    def test_node_lint_stage_collects_format_lint_and_typecheck_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "pnpm-lock.yaml").write_text("", encoding="utf-8")
            Path(tmp, "package.json").write_text(json.dumps({"scripts": {"format:check": "x", "lint": "x", "typecheck": "x", "test": "x"}}), encoding="utf-8")
            self.assertEqual(commands(build_plan(tmp))["lint"], [["pnpm", "run", "format:check"], ["pnpm", "run", "lint"], ["pnpm", "run", "typecheck"]])
            names = list(plan_to_config(build_plan(tmp), tmp).tasks)
            self.assertEqual(names, ["install", "lint", "lint-2", "lint-3", "test"])

    def test_rust_plan_is_locked_when_a_lockfile_exists(self) -> None:
        plan = commands(build_plan(FIXTURES / "rust"))
        self.assertIn("--locked", plan["test"][0])
        self.assertEqual(plan["lint"][0][:2], ["cargo", "clippy"])

    def test_java_prefers_maven_and_can_switch_to_gradle(self) -> None:
        self.assertEqual(commands(build_plan(FIXTURES / "java-maven"))["test"][0][-1], "verify")
        gradle = commands(build_plan(FIXTURES / "java-maven", "java", options={"build_tool": "gradle"}))
        self.assertEqual(gradle["test"][0][-1], "check")

    def test_dotnet_and_cmake_plans(self) -> None:
        self.assertEqual(commands(build_plan(FIXTURES / "dotnet"))["test"], [["dotnet", "test", "--no-build", "-c", "Release"]])
        cmake = commands(build_plan(FIXTURES / "c-cmake"))
        self.assertEqual(list(cmake), ["configure", "build", "test"])

    def test_make_project_only_gets_a_test_stage_when_a_test_target_exists(self) -> None:
        self.assertIn("test", commands(build_plan(FIXTURES / "c-make")))
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "Makefile").write_text("all:\n\ttrue\n", encoding="utf-8")
            with self.assertRaisesRegex(CIPlanError, "No test command"):
                build_plan(tmp)

    def test_python_plan_uses_unittest_and_exposes_the_source_directory(self) -> None:
        plan = build_plan(FIXTURES / "python")
        test = next(s for s in plan.steps if s.stage == "test")
        self.assertEqual(test.command[:4], ("python", "-m", "unittest", "discover"))
        self.assertEqual(dict(test.env), {"PYTHONPATH": "src"})
        pytest_plan = build_plan(FIXTURES / "python", options={"runner": "pytest"})
        self.assertEqual(next(s for s in pytest_plan.steps if s.stage == "test").command, ("python", "-m", "pytest"))

    def test_node_package_manager_is_chosen_from_the_lockfile(self) -> None:
        cases = {
            "pnpm-lock.yaml": ["pnpm", "install", "--frozen-lockfile"],
            "yarn.lock": ["yarn", "install", "--frozen-lockfile"],
            "bun.lock": ["bun", "install", "--frozen-lockfile"],
            "package-lock.json": ["npm", "ci"],
            "": ["npm", "install"],
        }
        for lockfile, install in cases.items():
            with self.subTest(lockfile=lockfile), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "package.json").write_text(json.dumps({"scripts": {"test": "node --test"}}), encoding="utf-8")
                if lockfile:
                    (root / lockfile).write_text("", encoding="utf-8")
                plan = build_plan(root)
                self.assertEqual(commands(plan)["install"], [install])
                self.assertEqual(plan.package_manager, install[0])

    def test_yarn_berry_uses_immutable_installs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text('{"scripts":{"test":"x"}}', encoding="utf-8")
            (root / "yarn.lock").write_text("", encoding="utf-8")
            (root / ".yarnrc.yml").write_text("nodeLinker: node-modules\n", encoding="utf-8")
            self.assertEqual(commands(build_plan(root))["install"], [["yarn", "install", "--immutable"]])

    def test_default_npm_placeholder_test_script_is_not_a_test(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(json.dumps({"scripts": {"test": 'echo "Error: no test specified" && exit 1'}}), encoding="utf-8")
            with self.assertRaisesRegex(CIPlanError, "No test command"):
                build_plan(root)

    def test_package_manager_option_wins_and_is_validated(self) -> None:
        self.assertEqual(build_plan(FIXTURES / "node", options={"package_manager": "pnpm"}).package_manager, "pnpm")
        with self.assertRaises(CIPlanError):
            build_plan(FIXTURES / "node", options={"package_manager": "pip"})


class OverrideTests(unittest.TestCase):
    def test_overrides_replace_a_stage_and_are_split_without_a_shell(self) -> None:
        plan = build_plan(FIXTURES / "go", overrides={"test": "go test -run 'Add|Sum' ./..."})
        self.assertEqual(commands(plan)["test"], [["go", "test", "-run", "Add|Sum", "./..."]])

    def test_skip_and_stages_select_the_stages_that_run(self) -> None:
        self.assertEqual([s.stage for s in build_plan(FIXTURES / "node", skip=["lint", "build"]).steps], ["install", "test"])
        self.assertEqual([s.stage for s in build_plan(FIXTURES / "node", stages=["test"]).steps], ["test"])

    def test_invalid_input_is_rejected(self) -> None:
        bad = [
            dict(language="cobol"),
            dict(overrides={"deploy": "echo hi"}),
            dict(overrides={"test": "   "}),
            dict(overrides={"test": "echo 'unterminated"}),
            dict(skip=["nope"]),
        ]
        for kwargs in bad:
            with self.subTest(**kwargs), self.assertRaises(CIPlanError):
                build_plan(FIXTURES / "go", **kwargs)

    def test_custom_language_requires_a_test_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(CIPlanError):
                build_plan(tmp, "custom")
            plan = build_plan(tmp, "custom", overrides={"test": "python -c pass"})
            self.assertEqual([s.stage for s in plan.steps], ["test"])

    def test_docker_needs_no_test_stage_but_other_languages_do(self) -> None:
        self.assertEqual([s.stage for s in build_plan(FIXTURES / "docker").steps], ["build"])
        with self.assertRaisesRegex(CIPlanError, "No test command"):
            build_plan(FIXTURES / "go", overrides={"build": "go build"}, stages=["build", "test"], skip=[], language="custom")


class ConfigConversionTests(unittest.TestCase):
    def test_plan_becomes_a_chained_task_graph(self) -> None:
        config = plan_to_config(build_plan(FIXTURES / "node"), FIXTURES / "node")
        self.assertEqual(list(config.tasks), ["install", "lint", "build", "test"])
        self.assertEqual(config.tasks["test"].depends_on, ("build",))
        self.assertEqual([t.name for t in config.plan(["test"])], ["install", "lint", "build", "test"])

    def test_stage_names_follow_the_documented_order(self) -> None:
        self.assertEqual(STAGES, ("install", "configure", "lint", "build", "test"))


class CliTests(unittest.TestCase):
    def test_dry_run_prints_the_plan_without_executing_it(self) -> None:
        proc = run_engine(FIXTURES / "go", "ci", "--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["language"], "go")
        self.assertEqual([s["stage"] for s in data["steps"]], ["install", "lint", "lint", "build", "test"])

    def test_detect_command(self) -> None:
        proc = run_engine(FIXTURES / "rust", "detect", "--json")
        self.assertEqual(json.loads(proc.stdout)["primary"], "rust")

    def test_failure_stops_later_stages_and_reports_them_as_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.json"
            proc = run_engine(Path(tmp), "ci", "--language", "custom", "--build-command", "python -c 'raise SystemExit(5)'",
                              "--test-command", "python -c pass", "--result", str(report))
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            data = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual([(t["name"], t["status"]) for t in data["tasks"]], [("build", "failed"), ("test", "skipped")])
            self.assertEqual(data["tasks"][0]["return_code"], 5)
            self.assertFalse(data["succeeded"])

    def test_plan_errors_exit_with_two(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run_engine(Path(tmp), "ci").returncode, 2)
            self.assertEqual(run_engine(Path(tmp), "ci", "--language", "custom", "--option", "bad").returncode, 2)

    def test_outputs_are_written_to_the_provider_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.env"
            env = {**os.environ, "PYTHONPATH": str(SRC), "PIPELINE_OUTPUT_FILE": str(out)}
            proc = subprocess.run([sys.executable, "-m", "pipeline", "ci", "--language", "custom", "--test-command", "python -c pass", "--root", tmp],
                                  env=env, capture_output=True, text=True, check=False)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(out.read_text(encoding="utf-8").splitlines(), ["language=custom", "package_manager=", "succeeded=true"])


@unittest.skipUnless(shutil.which("node") and shutil.which("npm"), "Node.js is not installed")
class NodeFixtureTest(unittest.TestCase):
    def test_node_fixture_passes_every_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = copy_fixture("node", Path(tmp))
            report = Path(tmp) / "report.json"
            proc = run_engine(project, "ci", "--result", str(report))
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual([t["name"] for t in json.loads(report.read_text(encoding="utf-8"))["tasks"]], ["install", "lint", "build", "test"])

    def test_a_failing_node_test_fails_the_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = copy_fixture("node", Path(tmp))
            (project / "index.test.js").write_text('require("node:test")("broken", () => { throw new Error("boom"); });\n', encoding="utf-8")
            self.assertEqual(run_engine(project, "ci").returncode, 1)


@unittest.skipUnless(shutil.which("go"), "Go is not installed")
class GoFixtureTest(unittest.TestCase):
    def test_go_fixture_passes_and_a_broken_one_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = copy_fixture("go", Path(tmp))
            self.assertEqual(run_engine(project, "ci").returncode, 0)
            (project / "demo.go").write_text("package demo\n\nfunc Add(a, b int) int { return a - b }\n", encoding="utf-8")
            self.assertEqual(run_engine(project, "ci").returncode, 1)


@unittest.skipUnless(shutil.which("cargo"), "Rust is not installed")
class RustFixtureTest(unittest.TestCase):
    def test_rust_fixture_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = copy_fixture("rust", Path(tmp))
            self.assertEqual(run_engine(project, "ci", "--skip", "lint").returncode, 0)


@unittest.skipUnless(shutil.which("make") and shutil.which("cc"), "make or a C compiler is not installed")
class CFixtureTest(unittest.TestCase):
    def test_make_fixture_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = copy_fixture("c-make", Path(tmp))
            self.assertEqual(run_engine(project, "ci").returncode, 0)


class PythonFixtureTest(unittest.TestCase):
    def test_python_fixture_passes_without_installing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = copy_fixture("python", Path(tmp))
            report = Path(tmp) / "report.json"
            proc = run_engine(project, "ci", "--skip", "install", "--result", str(report))
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual([t["name"] for t in json.loads(report.read_text(encoding="utf-8"))["tasks"]], ["build", "test"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
