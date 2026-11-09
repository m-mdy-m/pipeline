from __future__ import annotations

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

try:  # PyYAML is optional locally; CI installs it and sets PIPELINE_REQUIRE_YAML=1.
    import yaml
except ImportError:  # pragma: no cover - exercised only without PyYAML
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
ACTIONS = ROOT / ".github" / "actions"

NEW_WORKFLOWS = (
    "codeql.yml",
    "dependency-review.yml",
    "typos.yml",
    "yamllint.yml",
    "zizmor.yml",
    "pr-title.yml",
    "python-compatibility.yml",
    "scorecard.yml",
    "ci-main.yml",
    "toolchain-smoke.yml",
    "benchmark-regression.yml",
    "oci-publish.yml",
)
NEW_ACTIONS = (
    "python-quality",
    "run-pipeline",
    "toolchain-quality",
    "node-quality",
    "go-quality",
    "rust-quality",
    "java-quality",
    "dotnet-quality",
)
LANGUAGE_ACTIONS = ("node-quality", "go-quality", "rust-quality", "java-quality", "dotnet-quality")
EXTERNAL_USES = re.compile(r"^\s*uses:\s*([^\s#]+)", re.MULTILINE)




@unittest.skipIf(yaml is None, "PyYAML is not installed")
class YamllintConsumerPathTests(unittest.TestCase):
    def test_reusable_yamllint_skips_optional_paths_missing_from_consumers(self) -> None:
        workflow = load_yaml(WORKFLOWS / "yamllint.yml")
        steps = workflow["jobs"]["yamllint"]["steps"]
        lint_step = next(step for step in steps if step.get("name", "").startswith("Lint available"))
        script = lint_step["run"]

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / "examples").mkdir()
            bindir = root / "bin"
            bindir.mkdir()
            args_file = root / "yamllint-args.txt"
            stub = bindir / "yamllint"
            stub.write_text(
                '#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "$YAMLLINT_ARGS_FILE"\n',
                encoding="utf-8",
            )
            stub.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{bindir}{os.pathsep}{env.get('PATH', '')}"
            env["YAMLLINT_ARGS_FILE"] = str(args_file)

            result = subprocess.run(
                ["bash", "-euo", "pipefail", "-c", script],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            arguments = args_file.read_text(encoding="utf-8").splitlines()
            self.assertIn(".github/workflows", arguments)
            self.assertIn("examples", arguments)
            for absent in (
                ".gitlab-ci.yml",
                "src/pipeline/providers/gitlab/workflows",
                "zizmor.yml",
                ".github/dependabot.yml",
                ".github/actions",
            ):
                self.assertNotIn(absent, arguments)


class WorkflowInventoryTests(unittest.TestCase):
    def test_required_repository_workflows_exist(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        for name in NEW_WORKFLOWS:
            with self.subTest(workflow=name):
                self.assertTrue((WORKFLOWS / name).is_file())
                self.assertIn(f"'{name}'", makefile)

    def test_python_quality_action_is_used_by_compatibility_matrix(self) -> None:
        workflow = (WORKFLOWS / "python-compatibility.yml").read_text(encoding="utf-8")
        action = ACTIONS / "python-quality" / "action.yml"
        self.assertTrue(action.is_file())
        self.assertIn("uses: ./.github/actions/python-quality", workflow)

    def test_python_matrix_covers_all_supported_minors(self) -> None:
        workflow = (WORKFLOWS / "python-compatibility.yml").read_text(encoding="utf-8")
        for version in ('"3.11"', '"3.12"', '"3.13"'):
            with self.subTest(version=version):
                self.assertIn(version, workflow)

    def test_dependabot_tracks_action_and_python_updates(self) -> None:
        config = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
        self.assertIn("package-ecosystem: github-actions", config)
        self.assertIn("package-ecosystem: pip", config)
        self.assertIn("interval: weekly", config)


class WorkflowSecurityContractTests(unittest.TestCase):
    def test_new_external_action_references_are_version_tags_not_hashes(self) -> None:
        candidates = [WORKFLOWS / name for name in NEW_WORKFLOWS]
        candidates.extend(ACTIONS / name / "action.yml" for name in NEW_ACTIONS)
        for path in candidates:
            content = path.read_text(encoding="utf-8")
            for target in EXTERNAL_USES.findall(content):
                if target.startswith("./"):
                    continue
                with self.subTest(path=path.relative_to(ROOT), target=target):
                    self.assertIn("@", target, "External Actions must use an explicit version tag")
                    ref = target.rsplit("@", 1)[1]
                    self.assertRegex(ref, r"^v\d+(?:\.\d+)*(?:[-+][A-Za-z0-9.-]+)?$")
                    self.assertNotRegex(ref, r"^[0-9a-f]{40}$")

    def test_zizmor_explicitly_allows_tag_pinning(self) -> None:
        config = (ROOT / "zizmor.yml").read_text(encoding="utf-8")
        self.assertIn('"*": ref-pin', config)
        workflow = (WORKFLOWS / "zizmor.yml").read_text(encoding="utf-8")
        self.assertIn("config: zizmor.yml", workflow)

    def test_dependency_review_is_gated_by_repository_capability(self) -> None:
        workflow = (WORKFLOWS / "dependency-review.yml").read_text(encoding="utf-8")
        self.assertIn("vars.PIPELINE_DEPENDENCY_REVIEW_ENABLED == 'true'", workflow)
        self.assertIn("actions/dependency-review-action@v5.0.0", workflow)
        self.assertIn("dependency-review-prerequisite:", workflow)

    def test_read_only_default_permissions_are_declared(self) -> None:
        for name in NEW_WORKFLOWS:
            workflow = (WORKFLOWS / name).read_text(encoding="utf-8")
            with self.subTest(workflow=name):
                self.assertRegex(workflow, r"(?m)^permissions:\n  contents: read(?:\n|$)")


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def triggers(workflow: dict) -> dict:
    # YAML 1.1 parses the bare key `on` as the boolean True.
    return workflow.get("on", workflow.get(True)) or {}


def all_steps(document: dict) -> list[dict]:
    if "runs" in document:
        return document["runs"].get("steps", [])
    return [step for job in document.get("jobs", {}).values() for step in job.get("steps", [])]


@unittest.skipIf(yaml is None and not os.environ.get("PIPELINE_REQUIRE_YAML"), "PyYAML is not installed")
class StructuralContractTests(unittest.TestCase):
    """Offline substitutes for actionlint: broken references fail on every push."""

    def test_pyyaml_is_available_when_required(self) -> None:
        if os.environ.get("PIPELINE_REQUIRE_YAML"):
            self.assertIsNotNone(yaml, "PIPELINE_REQUIRE_YAML is set but PyYAML cannot be imported")

    def test_every_workflow_and_action_is_valid_yaml_with_the_required_keys(self) -> None:
        for path in sorted(WORKFLOWS.glob("*.yml")):
            with self.subTest(path=path.name):
                document = load_yaml(path)
                self.assertIn("name", document)
                self.assertTrue(triggers(document), "workflow has no triggers")
                self.assertTrue(document.get("jobs"))
        for path in sorted(ACTIONS.glob("*/action.yml")):
            with self.subTest(path=path.parent.name):
                document = load_yaml(path)
                self.assertTrue(document.get("name") and document.get("description"))
                self.assertEqual(document["runs"]["using"], "composite")

    def test_composite_run_steps_declare_a_shell(self) -> None:
        for path in sorted(ACTIONS.glob("*/action.yml")):
            for step in all_steps(load_yaml(path)):
                if "run" in step:
                    with self.subTest(action=path.parent.name, step=step.get("name")):
                        self.assertIn("shell", step)

    def test_expressions_only_reference_declared_inputs(self) -> None:
        for path in sorted(ACTIONS.glob("*/action.yml")):
            text = path.read_text(encoding="utf-8")
            declared = set(load_yaml(path).get("inputs", {}))
            used = set(re.findall(r"inputs\.([A-Za-z0-9_-]+)", text))
            with self.subTest(action=path.parent.name):
                self.assertEqual(used - declared, set(), "undeclared inputs are referenced")
                self.assertEqual(declared - used, set(), "declared inputs are never used")
        for path in sorted(WORKFLOWS.glob("*.yml")):
            document = load_yaml(path)
            call = triggers(document).get("workflow_call")
            if call is None:
                continue
            declared = set((call or {}).get("inputs", {}))
            used = set(re.findall(r"inputs\.([A-Za-z0-9_-]+)", path.read_text(encoding="utf-8")))
            with self.subTest(workflow=path.name):
                self.assertEqual(used - declared, set(), "undeclared inputs are referenced")

    def test_step_output_references_point_to_existing_step_ids(self) -> None:
        for path in [*sorted(ACTIONS.glob("*/action.yml")), *sorted(WORKFLOWS.glob("*.yml"))]:
            document = load_yaml(path)
            ids = {step["id"] for step in all_steps(document) if "id" in step}
            referenced = set(re.findall(r"steps\.([A-Za-z0-9_-]+)\.", path.read_text(encoding="utf-8")))
            with self.subTest(path=str(path.relative_to(ROOT))):
                self.assertEqual(referenced - ids, set())

    def test_job_needs_reference_existing_jobs(self) -> None:
        for path in sorted(WORKFLOWS.glob("*.yml")):
            jobs = load_yaml(path).get("jobs", {})
            for name, job in jobs.items():
                needs = job.get("needs", [])
                needs = [needs] if isinstance(needs, str) else needs
                with self.subTest(workflow=path.name, job=name):
                    self.assertEqual(set(needs) - set(jobs), set())

    def test_local_uses_references_exist_and_reusable_workflows_are_callable(self) -> None:
        for path in [*sorted(WORKFLOWS.glob("*.yml")), *sorted(ACTIONS.glob("*/action.yml"))]:
            for target in re.findall(r"uses:\s*(\./\.github/[^\s#]+)", path.read_text(encoding="utf-8")):
                with self.subTest(path=path.name, target=target):
                    resolved = ROOT / target[2:]
                    if resolved.suffix == ".yml":
                        self.assertTrue(resolved.is_file())
                        self.assertIn("workflow_call", triggers(load_yaml(resolved)))
                    else:
                        self.assertTrue((resolved / "action.yml").is_file())

    def test_called_workflows_receive_only_declared_inputs(self) -> None:
        for path in sorted(WORKFLOWS.glob("*.yml")):
            for name, job in load_yaml(path).get("jobs", {}).items():
                target = job.get("uses", "")
                if not target.startswith("./.github/workflows/"):
                    continue
                call = triggers(load_yaml(ROOT / target[2:])).get("workflow_call") or {}
                declared = set(call.get("inputs", {}))
                with self.subTest(workflow=path.name, job=name):
                    self.assertEqual(set(job.get("with", {})) - declared, set())
                    required = {k for k, v in call.get("inputs", {}).items() if v.get("required")}
                    self.assertEqual(required - set(job.get("with", {})), set())

    def test_local_action_calls_only_pass_declared_inputs(self) -> None:
        for path in sorted(WORKFLOWS.glob("*.yml")):
            for step in all_steps(load_yaml(path)):
                target = step.get("uses", "")
                if not target.startswith("./.github/actions/"):
                    continue
                action = load_yaml(ROOT / target[2:] / "action.yml")
                inputs = action.get("inputs", {})
                with self.subTest(workflow=path.name, step=step.get("name") or target):
                    self.assertEqual(set(step.get("with", {})) - set(inputs), set())
                    required = {k for k, v in inputs.items() if v.get("required")}
                    self.assertEqual(required - set(step.get("with", {})), set())


@unittest.skipIf(yaml is None and not os.environ.get("PIPELINE_REQUIRE_YAML"), "PyYAML is not installed")
class PushGateContractTests(unittest.TestCase):
    def test_main_ci_runs_on_every_push_pull_request_and_merge_queue(self) -> None:
        on = triggers(load_yaml(WORKFLOWS / "ci-main.yml"))
        self.assertEqual(on["push"]["branches"], ["**"])
        for event in ("pull_request", "merge_group", "workflow_dispatch"):
            self.assertIn(event, on)

    def test_gate_job_waits_for_every_other_job_and_always_runs(self) -> None:
        jobs = load_yaml(WORKFLOWS / "ci-main.yml")["jobs"]
        gate = jobs["gate"]
        self.assertEqual(set(gate["needs"]), set(jobs) - {"gate"})
        self.assertEqual(str(gate["if"]), "always()")

    def test_main_ci_covers_unit_tests_toolchains_contracts_and_lint(self) -> None:
        jobs = load_yaml(WORKFLOWS / "ci-main.yml")["jobs"]
        called = {job.get("uses") for job in jobs.values()}
        for workflow in ("python-compatibility.yml", "toolchain-smoke.yml", "yamllint.yml", "typos.yml", "docs-check.yml", "ci.yml"):
            self.assertIn(f"./.github/workflows/{workflow}", called)

    def test_toolchain_smoke_exercises_every_language_action_and_a_negative_control(self) -> None:
        text = (WORKFLOWS / "toolchain-smoke.yml").read_text(encoding="utf-8")
        for action in (*LANGUAGE_ACTIONS, "python-quality", "toolchain-quality"):
            with self.subTest(action=action):
                self.assertIn(f"uses: ./.github/actions/{action}", text)
        self.assertIn("continue-on-error: true", text)
        self.assertIn('test "$OUTCOME" = "failure"', text)

    def test_every_smoke_fixture_is_covered_by_the_matrix(self) -> None:
        text = (WORKFLOWS / "toolchain-smoke.yml").read_text(encoding="utf-8")
        for fixture in sorted(p.name for p in (ROOT / "examples" / "toolchains").iterdir() if p.is_dir()):
            with self.subTest(fixture=fixture):
                self.assertIn(f"fixture: {fixture}", text)

    def test_language_actions_run_the_shared_engine_and_nothing_else(self) -> None:
        for name in (*LANGUAGE_ACTIONS, "toolchain-quality", "python-quality"):
            text = (ACTIONS / name / "action.yml").read_text(encoding="utf-8")
            with self.subTest(action=name):
                self.assertIn("python -m pipeline.providers.github", text)
                self.assertIn("github.action_path }}/../../../src", text)

    def test_same_action_is_pinned_to_the_same_version_everywhere(self) -> None:
        versions: dict[str, set[str]] = {}
        for path in [*WORKFLOWS.glob("*.yml"), *ACTIONS.glob("*/action.yml")]:
            for target in EXTERNAL_USES.findall(path.read_text(encoding="utf-8")):
                if not target.startswith("./") and path.name in {f for f in NEW_WORKFLOWS} | {"action.yml"}:
                    name, ref = target.rsplit("@", 1)
                    versions.setdefault(name, set()).add(ref)
        for name in ("actions/setup-go", "actions/setup-node", "actions/setup-java", "actions/setup-dotnet", "actions/setup-python"):
            with self.subTest(action=name):
                major = {ref.split(".")[0] for ref in versions.get(name, set())}
                self.assertLessEqual(len(major), 1, f"{name} is pinned to different majors: {versions[name]}")


if __name__ == "__main__":
    unittest.main(verbosity=2)


def declared_inputs(spec: dict) -> set[str]:
    if "runs" in spec:
        return set(spec.get("inputs") or {})
    triggers = spec.get("on", spec.get(True)) or {}
    return set(((triggers.get("workflow_call") or {}).get("inputs")) or {})


@unittest.skipIf(yaml is None and not os.environ.get("PIPELINE_REQUIRE_YAML"), "PyYAML is not installed")
class ProjectExampleTests(unittest.TestCase):
    """Every per-project example must only pass inputs the local actions declare."""

    def test_example_inputs_are_declared(self) -> None:
        root = Path(__file__).resolve().parents[1]
        prefix = "m-mdy-m/pipeline/"
        files = sorted((root / "examples" / "projects").glob("*/ci.yml"))
        self.assertTrue(files)
        problems: list[str] = []
        for path in files:
            doc = load_yaml(path)
            for job_name, job in (doc.get("jobs") or {}).items():
                if "uses" in job:
                    steps = [{"uses": job["uses"], "with": job.get("with")}]
                else:
                    steps = job.get("steps", [])
                for step in steps:
                    uses = str(step.get("uses", ""))
                    if not uses.startswith(prefix):
                        continue
                    target = uses[len(prefix):].split("@", 1)[0]
                    local = root / target
                    if local.is_dir():
                        local = local / "action.yml"
                    where = f"{path.parent.name}/{job_name}"
                    if not local.exists():
                        problems.append(f"{where}: {target} does not exist")
                        continue
                    declared = declared_inputs(load_yaml(local))
                    for key in step.get("with") or {}:
                        if key not in declared:
                            problems.append(f"{where}: unknown input {key!r} for {target}")
        self.assertEqual(problems, [])
