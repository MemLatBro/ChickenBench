import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("analyze_launcher", ROOT / "scripts" / "analyze_launcher.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class LauncherTests(unittest.TestCase):
    def test_blank_input_uses_default(self):
        self.assertEqual(launcher.validate_baseline("  "), "JEDEC")

    def test_valid_labels_match_capture_label_alphabet(self):
        for label in ["JEDEC", "TUNED", "DDR5_6000-CL30", "-config"]:
            with self.subTest(label=label):
                self.assertEqual(launcher.validate_baseline(label), label)

    def test_spaces_and_shell_metacharacters_are_rejected(self):
        for label in ["MY CONFIG", "JEDEC & echo hello", "x|echo", "x>out", "x<in", 'x"y',
                      "x%PATH%", "x!PATH!", "x;y", "x\ny", "x(y)", "x`y", "x$y"]:
            with self.subTest(label=label), self.assertRaises(ValueError):
                launcher.validate_baseline(label)

    def test_command_keeps_paths_with_spaces_and_leading_hyphen_label(self):
        with mock.patch.object(launcher, "ROOT", Path("folder with spaces")):
            command = launcher.analyzer_command("-config")
        self.assertEqual(command, [sys.executable, str(Path("folder with spaces/analysis/cb_analyze.py")),
                                   str(Path("folder with spaces/Results")), "--baseline=-config"])

    def test_invalid_prompt_does_not_launch_any_process(self):
        with mock.patch("builtins.input", return_value="JEDEC & echo hello"), \
             mock.patch.object(launcher.subprocess, "run") as run, \
             contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            launcher.main([])
        self.assertEqual(error.exception.code, 2)
        run.assert_not_called()

    def test_failed_analysis_never_opens_stale_report(self):
        with mock.patch.object(launcher.subprocess, "run", return_value=subprocess.CompletedProcess([], 2)) as run, \
             mock.patch.object(launcher, "open_report") as opened, \
             contextlib.redirect_stderr(io.StringIO()):
            result = launcher.main(["--baseline=JEDEC"])
        self.assertEqual(result, 2)
        self.assertIs(run.call_args.kwargs["shell"], False)
        opened.assert_not_called()

    def test_success_opens_new_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Results").mkdir()
            report = root / "Results/report.html"
            report.write_text("test", encoding="utf-8")
            with mock.patch.object(launcher, "ROOT", root), \
                 mock.patch.object(launcher.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)), \
                 mock.patch.object(launcher, "open_report") as opened:
                self.assertEqual(launcher.main(["--baseline=JEDEC"]), 0)
                opened.assert_called_once_with(report)

    def test_success_without_report_is_failure(self):
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(launcher, "ROOT", Path(directory)), \
             mock.patch.object(launcher.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)), \
             mock.patch.object(launcher, "open_report") as opened, \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(launcher.main(["--baseline=JEDEC"]), 1)
            opened.assert_not_called()

    def test_batch_does_not_read_or_expand_label(self):
        text = (ROOT / "CB_Analyze.bat").read_text().lower()
        self.assertNotIn("set /p", text)
        self.assertNotIn("%base%", text)
        self.assertIn("analyze_launcher.py", text)


if __name__ == "__main__":
    unittest.main()
