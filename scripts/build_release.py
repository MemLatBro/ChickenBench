#!/usr/bin/env python3
"""Build a source ZIP without captures, installed binaries, or local caches."""
import argparse
import os
from pathlib import Path
import re
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".vscode", ".idea",
                 "Results", "analysis_backups", "dist", "build", "htmlcov", "DemoResults",
                 "DemoAnalysis", "Analysis", "ReplayResults", "ReplayAnalysis", "OriginalCaptures"}
EXCLUDED_SUFFIXES = {".exe", ".dll", ".sys", ".vpk", ".pyc", ".pyo", ".zip", ".log"}
EXCLUDED_NAMES = {".DS_Store", "Thumbs.db", ".coverage", ".env"}


def release_files(root):
    root = Path(root).resolve()
    for directory, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS and not (Path(directory) / d).is_symlink())
        for name in sorted(files):
            path = Path(directory) / name
            if path.is_symlink() or name in EXCLUDED_NAMES or path.suffix.lower() in EXCLUDED_SUFFIXES:
                continue
            yield path


def build_archive(root=ROOT, output=None):
    root = Path(root).resolve()
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?", version) is None:
        raise ValueError("VERSION must contain a release version such as 1.0.8")
    prefix = "ChickenBench-v" + version
    output = Path(output) if output is not None else root / "dist" / (prefix + "-github.zip")
    if output.suffix.lower() != ".zip":
        raise ValueError("Release output must have a .zip extension")
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in release_files(root):
            archive.write(path, (Path(prefix) / path.relative_to(root)).as_posix())
    return output.resolve()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="output ZIP path; default: dist/ChickenBench-v<VERSION>-github.zip")
    args = parser.parse_args()
    print(build_archive(output=args.output))
