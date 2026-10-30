from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pipeline.release.target import (  # noqa: E402
    ReleaseTargetError,
    _resolve_shell,
    execute_target_stage,
    render_target_summary,
)


class ReleaseTargetTests(unittest.TestCase):
    def test_windows_msys2_uses_its_own_bash_not_system_wsl_bash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "msys64"
            bash = root / "usr" / "bin" / "bash.exe"
            bash.parent.mkdir(parents=True)
            bash.write_bytes(b"test executable")
            (root / "ucrt64" / "bin").mkdir(parents=True)

            environment = {
                "MSYSTEM": "UCRT64",
                "MSYS2_LOCATION": str(root),
                "PATH": "C:\\Windows\\System32",
            }
            resolved = _resolve_shell("bash", environment, platform_name="win32")

            self.assertEqual(resolved, str(bash))
            self.assertTrue(environment["PATH"].startswith(
                f"{root / 'ucrt64' / 'bin'};{root / 'usr' / 'bin'};"
            ))
            self.assertEqual(environment["MSYS2_PATH_TYPE"], "inherit")
            self.assertEqual(environment["CHERE_INVOKING"], "1")

    def test_windows_msys2_discovers_default_runner_temp_installation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runner_temp = Path(tmp) / "runner-temp"
            root = runner_temp / "msys64"
            bash = root / "usr" / "bin" / "bash.exe"
            bash.parent.mkdir(parents=True)
            bash.write_bytes(b"test executable")
            (root / "clangarm64" / "bin").mkdir(parents=True)

            environment = {
                "MSYSTEM": "CLANGARM64",
                "RUNNER_TEMP": str(runner_temp),
                "PATH": "C:\\Windows\\System32",
            }
            resolved = _resolve_shell("bash", environment, platform_name="win32")

            self.assertEqual(resolved, str(bash))
            self.assertTrue(environment["PATH"].startswith(
                f"{root / 'clangarm64' / 'bin'};{root / 'usr' / 'bin'};"
            ))

    def test_non_msys2_shell_resolution_is_unchanged(self) -> None:
        environment = {"PATH": "/usr/bin"}
        self.assertEqual(
            _resolve_shell("bash", environment, platform_name="win32"),
            "bash",
        )

    def test_target_stage_streams_and_records_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = execute_target_stage(
                target="linux-amd64",
                stage="test",
                command="printf 'visible test output\\n'",
                workspace=root,
                report_directory=".reports",
            )
            report = root / ".reports" / "linux-amd64" / "test.json"
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(payload["exit_code"], 0)
            self.assertEqual(payload["stage"], "test")

    def test_target_stage_records_failure_and_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = execute_target_stage(
                target="windows-amd64",
                stage="build",
                command="printf 'diagnostic line\\n'; exit 17",
                workspace=root,
                report_directory=".reports",
            )
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["exit_code"], 17)
            self.assertIn("status 17", result["error"])

    def test_summary_includes_both_stages_and_failure_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for stage, command in (("test", "true"), ("build", "echo package-error >&2; exit 1")):
                execute_target_stage(
                    target="darwin-arm64",
                    stage=stage,
                    command=command,
                    workspace=root,
                    report_directory=".reports",
                )
            summary = render_target_summary(
                target="darwin-arm64",
                workspace=root,
                report_directory=".reports",
            )
            self.assertIn("Release target: `darwin-arm64`", summary)
            self.assertIn("| test | succeeded | 0 |", summary)
            self.assertIn("| build | failed | 1 |", summary)
            self.assertIn("build", summary)
            self.assertIn("status 1", summary)

    def test_invalid_target_and_workspace_escape_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ReleaseTargetError):
                execute_target_stage(
                    target="../outside",
                    stage="test",
                    command="true",
                    workspace=root,
                )
            with self.assertRaises(ReleaseTargetError):
                execute_target_stage(
                    target="linux-amd64",
                    stage="test",
                    command="true",
                    workspace=root,
                    working_directory="../outside",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
