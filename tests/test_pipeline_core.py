from __future__ import annotations
import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SCRIPTS=ROOT/"scripts";sys.path.insert(0,str(SCRIPTS))
from pipeline_core.artifacts import LocalArtifactStore
from pipeline_core.config import PipelineConfig
from pipeline_core.context import PipelineContext
from pipeline_core.errors import ArtifactError,PipelineConfigError
from pipeline_core.provider import ProviderAdapter
from pipeline_core.runner import TaskRunner
from providers.github.adapter import GitHubAdapter
from providers.gitlab.adapter import GitLabAdapter
from providers.local.adapter import LocalAdapter

def write_config(root:Path,tasks:str)->Path:
    path=root/"pipeline.toml";path.write_text('schema_version = 1\n[project]\nname = "fixture"\n'+tasks,encoding="utf-8");return path
class ContextTests(unittest.TestCase):
    def test_core_ignores_provider_specific_environment(self):
        value=PipelineContext.from_environment({"GITHUB_REF_TYPE":"tag","GITHUB_REF_NAME":"v9.9.9","GITHUB_SHA":"wrong"},workspace=ROOT)
        self.assertEqual(value.provider,"local");self.assertEqual(value.ref_type,"");self.assertEqual(value.sha,"")
    def test_context_roundtrip(self):
        value=PipelineContext.from_environment({"PIPELINE_PROVIDER":"gitlab","PIPELINE_REF_TYPE":"tag","PIPELINE_REF_NAME":"v1.2.3","PIPELINE_SHA":"a"*40},workspace=ROOT)
        result=PipelineContext.from_environment(value.to_environment(),workspace=ROOT)
        self.assertEqual(result.ref_name,"v1.2.3");self.assertEqual(result.sha,"a"*40)
    def test_invalid_provider_name_is_rejected(self):
        with self.assertRaises(ValueError):PipelineContext.from_environment({"PIPELINE_PROVIDER":"GitHub"},workspace=ROOT)
class ProviderTests(unittest.TestCase):
    def test_all_adapters_share_contract(self):
        for adapter in (GitHubAdapter(),GitLabAdapter(),LocalAdapter()):self.assertIsInstance(adapter,ProviderAdapter)
    def test_github_maps_tag_and_output(self):
        v=GitHubAdapter().normalize_environment({"GITHUB_WORKSPACE":str(ROOT),"GITHUB_REF":"refs/tags/v1.2.3","GITHUB_SHA":"a"*40,"GITHUB_REPOSITORY":"group/project","GITHUB_OUTPUT":"/tmp/out"})
        self.assertEqual((v["PIPELINE_PROVIDER"],v["PIPELINE_REF_TYPE"],v["PIPELINE_REF_NAME"]),("github","tag","v1.2.3"))
        self.assertEqual(v["PIPELINE_OUTPUT_FILE"],"/tmp/out")
    def test_github_submodule_credentials_are_provider_scoped(self):
        adapter=GitHubAdapter();base={"GITHUB_WORKSPACE":str(ROOT),"GITHUB_REF":"refs/heads/main","SOURCE_SUBMODULE_TOKEN":"token"}
        self.assertNotIn("GIT_CONFIG_COUNT",adapter.bootstrap_values({**base,"SOURCE_SUBMODULE_MODE":"omit"}))
        data=adapter.bootstrap_values({**base,"SOURCE_SUBMODULE_MODE":"recursive"})
        self.assertEqual(data["GIT_CONFIG_COUNT"],"1");self.assertEqual(data["PIPELINE_SECRET_REDACTIONS"],"token")
    def test_gitlab_maps_its_own_ci_variables(self):
        v=GitLabAdapter().normalize_environment({"CI_PROJECT_DIR":str(ROOT),"CI_PROJECT_PATH":"group/project","CI_COMMIT_TAG":"v2.0.0","CI_COMMIT_SHA":"b"*40,"GITHUB_SHA":"wrong"})
        self.assertEqual((v["PIPELINE_PROVIDER"],v["PIPELINE_REF_TYPE"],v["PIPELINE_REF_NAME"],v["PIPELINE_SHA"]),("gitlab","tag","v2.0.0","b"*40))
    def test_business_logic_does_not_contain_provider_env_references(self):
        for directory in (SCRIPTS/"pipeline_core",SCRIPTS/"pipeline_release"):
            for path in directory.glob("*.py"):
                content=path.read_text(encoding="utf-8")
                with self.subTest(path=path.name):
                    self.assertNotIn("GITHUB_",content);self.assertNotIn("GITLAB_",content);self.assertNotIn("::warning title=",content)

class AdapterExecutionTests(unittest.TestCase):
    """The same task graph must run through the three provider entrypoints."""
    def test_same_task_graph_executes_through_local_github_and_gitlab(self):
        cases = {
            "local": {},
            "github": {"GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/main",
                       "GITHUB_SHA": "a" * 40, "GITHUB_REPOSITORY": "example/project"},
            "gitlab": {"CI_PIPELINE_SOURCE": "push", "CI_COMMIT_BRANCH": "main",
                       "CI_COMMIT_REF_NAME": "main", "CI_COMMIT_SHA": "b" * 40,
                       "CI_PROJECT_PATH": "example/project", "GITHUB_SHA": "must-not-win"},
        }
        entrypoints = {
            "local": SCRIPTS / "providers" / "local" / "adapter.py",
            "github": SCRIPTS / "providers" / "github" / "adapter.py",
            "gitlab": SCRIPTS / "providers" / "gitlab" / "adapter.py",
        }
        for provider, values in cases.items():
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                config_text = f"""
[tasks.prepare]
command = ["python", "-c", "from pathlib import Path; Path('marker.txt').write_text('ok')"]

[tasks.verify]
command = ["python", "-c", "import os; from pathlib import Path; assert Path('marker.txt').read_text() == 'ok'; assert os.environ['PIPELINE_PROVIDER'] == '{provider}'; assert os.environ['PIPELINE_WORKSPACE'] == str(Path.cwd())"]
depends_on = ["prepare"]
"""
                config = write_config(root, config_text)
                report_path = root / "run-report.json"
                child_env = {key: value for key, value in os.environ.items() if not key.startswith("PIPELINE_")}
                child_env["PWD"] = str(root)
                child_env.update(values)
                if provider == "local":
                    child_env["PIPELINE_WORKSPACE"] = str(root)
                elif provider == "github":
                    child_env["GITHUB_WORKSPACE"] = str(root)
                else:
                    child_env["CI_PROJECT_DIR"] = str(root)

                command = [sys.executable, str(entrypoints[provider])]
                if provider == "github":
                    command += ["task", "verify"]
                else:
                    command += ["run", "verify"]
                command += ["--root", str(root), "--config", str(config),
                            "--result", str(report_path), "--json"]
                completed = subprocess.run(command, cwd=ROOT, env=child_env, capture_output=True, text=True, check=False)
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                report = json.loads(report_path.read_text(encoding="utf-8"))
                self.assertTrue(report["succeeded"], report)
                self.assertEqual(report["provider"], provider)
                self.assertEqual([item["name"] for item in report["tasks"]], ["prepare", "verify"])
                self.assertTrue((root / "marker.txt").is_file())

class ConfigTests(unittest.TestCase):
    def test_config_plans_dependencies_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cfg=write_config(root,'[tasks.prepare]\ncommand=["python","-c","pass"]\n[tasks.check]\ncommand=["python","-c","pass"]\ndepends_on=["prepare"]\n')
            self.assertEqual([x.name for x in PipelineConfig.load(cfg,workspace=root).plan(["check"])],["prepare","check"])
    def test_unknown_dependency_cycle_shell_string_and_path_escape_fail(self):
        samples=[
            '[tasks.x]\ncommand=["python","-c","pass"]\ndepends_on=["missing"]\n',
            '[tasks.x]\ncommand=["python","-c","pass"]\ndepends_on=["y"]\n[tasks.y]\ncommand=["python","-c","pass"]\ndepends_on=["x"]\n',
            '[tasks.x]\ncommand="echo unsafe"\n',
            '[tasks.x]\ncommand=["python","-c","pass"]\nworking_directory="../outside"\n']
        for text in samples:
            with tempfile.TemporaryDirectory() as tmp:
                with self.subTest(text=text),self.assertRaises(PipelineConfigError):PipelineConfig.load(write_config(Path(tmp),text),workspace=Path(tmp))
    def test_reserved_environment_cannot_override_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=write_config(Path(tmp),'[tasks.x]\ncommand=["python","-c","pass"]\n[tasks.x.env]\nPIPELINE_SHA="spoof"\n')
            with self.assertRaises(PipelineConfigError):PipelineConfig.load(cfg,workspace=Path(tmp))
class RunnerTests(unittest.TestCase):
    def test_dependency_task_execution_receives_portable_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cfg=write_config(root,"""
[tasks.prepare]
command=["python","-c","from pathlib import Path; Path('marker.txt').write_text('ok')"]
[tasks.check]
command=["python","-c","import os; from pathlib import Path; assert Path('marker.txt').read_text() == 'ok'; assert os.environ['PIPELINE_PROVIDER'] == 'local'"]
depends_on=["prepare"]
""")
            report=TaskRunner(PipelineConfig.load(cfg,workspace=root),PipelineContext.from_environment({},workspace=root)).run(["check"])
            self.assertTrue(report.succeeded);self.assertEqual([x.name for x in report.results],["prepare","check"])
    def test_failed_dependency_skips_downstream_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cfg=write_config(root,"""
[tasks.fail]
command=["python","-c","raise SystemExit(7)"]
[tasks.next]
command=["python","-c","print('must not execute')"]
depends_on=["fail"]
""")
            report=TaskRunner(PipelineConfig.load(cfg,workspace=root),PipelineContext.from_environment({},workspace=root)).run(["next"])
            self.assertEqual([x.status for x in report.results],["failed","skipped"]);self.assertEqual(report.exit_code,1)
    def test_timeout_returns_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cfg=write_config(root,'[tasks.slow]\ncommand=["python","-c","import time; time.sleep(3)"]\ntimeout_seconds=1\n')
            report=TaskRunner(PipelineConfig.load(cfg,workspace=root),PipelineContext.from_environment({},workspace=root)).run(["slow"])
            self.assertEqual(report.results[0].return_code,124)
class ArtifactTests(unittest.TestCase):
    def test_artifacts_are_copied_hashed_and_manifested(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);src=root/"source.zip";src.write_bytes(b"payload")
            entries=LocalArtifactStore(root/"out").publish([src])
            self.assertEqual((root/"out"/"source.zip").read_bytes(),b"payload")
            self.assertEqual(len(entries[0].sha256),64)
            self.assertEqual(json.loads((root/"out"/"artifacts.json").read_text())["artifacts"][0]["name"],"source.zip")
    def test_duplicate_casefold_names_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"a").mkdir();(root/"b").mkdir();a=root/"a"/"x.zip";b=root/"b"/"X.ZIP";a.write_text("a");b.write_text("b")
            with self.assertRaises(ArtifactError):LocalArtifactStore(root/"out").publish([a,b])
    def test_cli_runs_temporary_config_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cfg=write_config(root,"""
[tasks.emit]
command=["python","-c","from pathlib import Path; Path('result.txt').write_text('ok')"]
[tasks.verify]
command=["python","-c","from pathlib import Path; assert Path('result.txt').read_text() == 'ok'"]
depends_on=["emit"]
""")
            result=root/"report.json";import subprocess
            proc=subprocess.run([sys.executable,str(SCRIPTS/"pipeline.py"),"run","verify","--root",str(root),"--config",str(cfg),"--result",str(result),"--json"],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr);self.assertTrue(json.loads(result.read_text())["succeeded"])
if __name__=="__main__":unittest.main(verbosity=2)
