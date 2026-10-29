import importlib.util
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_release", ROOT / "scripts/build_release.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class ReleaseLayoutTests(unittest.TestCase):
    def test_runtime_paths_exist(self):
        for relative in ["runner/cb_runner.ps1", "analysis/cb_analyze.py", "config/cb_settings.ini",
                         "config/cs2_cfg/cb_s01.cfg", "config/cs2_cfg/cb_s20.cfg",
                         "scripts/analyze_launcher.py", "LICENSE", "THIRD_PARTY_NOTICES.md"]:
            with self.subTest(path=relative):
                self.assertTrue((ROOT / relative).is_file())
        runner = (ROOT / "runner/cb_runner.ps1").read_text()
        self.assertIn("Split-Path -Parent $PSScriptRoot", runner)
        self.assertIn("config\\cb_settings.ini", runner)
        self.assertIn("config\\cs2_cfg\\cb_s{0:D2}.cfg", runner)

    def test_archive_includes_source_and_workflow_but_excludes_runtime_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source folder"
            root.mkdir()
            (root / "VERSION").write_text("1.0.8\n")
            included = ["README.md", "LICENSE", ".github/workflows/tests.yml", "analysis/test.py", "examples/data.csv"]
            excluded = ["Results/private.csv", "tools/PresentMon.exe", "tools/unexpected.DLL", "config/map.vpk",
                        "analysis/__pycache__/cached.pyc", ".git/config", "dist/old.zip", "DemoResults/frames.csv"]
            for name in included + excluded:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("test")
            archive = builder.build_archive(root)
            with ZipFile(archive) as zipped:
                names = set(zipped.namelist())
            prefix = "ChickenBench-v1.0.8/"
            for name in included:
                self.assertIn(prefix + name, names)
            for name in excluded:
                self.assertNotIn(prefix + name, names)

    def test_grouped_source_keeps_analyzer_versions_and_formula_files(self):
        self.assertIn("VERSION = '1.2.0'", (ROOT / "analysis/cb_analyze.py").read_text())
        self.assertIn("FORMULA_VERSION = '1.1.0'", (ROOT / "analysis/cb_formulas.py").read_text())


if __name__ == "__main__":
    unittest.main()
