"""Run the golden cases against an implementation of omitnix and compare what it does.

An implementation is any command that behaves like ``omitnix``. The reference is the Python
version (``python -m omitnix``). Each case in ``rewrite/golden/cases/<name>/`` is a small
repository (or a directory of repositories), the command-line arguments to run it with, and
what the reference produced: the exit status, standard output, standard error and the
documents it wrote. See ``rewrite/golden/README.md`` for the format.

    python rewrite/tools/run_golden.py --cmd "python -m omitnix"
    python rewrite/tools/run_golden.py --cmd ./target/release/omitnix --cases c01_php,w01_basic
    python rewrite/tools/run_golden.py --cmd "python -m omitnix" --record   # refresh expected

Standard library only. Needs ``git`` on the PATH, because most cases are git working trees.

Output is a pass or fail per case with category counts for a failed document, and never the
content of a document. ``--show-details`` adds the paths behind each category and a unified
diff of a stream that differed; the golden data is synthetic, so that is safe here.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import compare_index  # noqa: E402

GOLDEN = Path(__file__).resolve().parent.parent / "golden"
CASES = GOLDEN / "cases"

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "golden",
    "GIT_AUTHOR_EMAIL": "golden@example.invalid",
    "GIT_COMMITTER_NAME": "golden",
    "GIT_COMMITTER_EMAIL": "golden@example.invalid",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
}


@dataclass
class Result:
    name: str
    problems: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.problems


def _git(directory: Path, *args: str) -> None:
    env = {**os.environ, **_GIT_ENV}
    completed = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-c", "core.safecrlf=false", *args],
        cwd=directory,
        capture_output=True,
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {message}")


def _make_repository(directory: Path) -> None:
    _git(directory, "init", "-q", "-b", "main")
    _git(directory, "add", "-A")
    _git(directory, "commit", "-q", "-m", "base", "--allow-empty")
    _git(directory, "tag", "base")


def _copy_tree(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, target, dirs_exist_ok=True)


_LABELLED_PATH = re.compile(r"(<(?:ROOT|OUT)>)(\S*)")


def _normalise(text: str, replacements: list[tuple[str, str]], *, line_ends: bool = True) -> str:
    """Make a stream the same on every platform: no machine paths, no CRLF, one slash.

    ``line_ends=False`` leaves carriage returns alone, for a document whose line ends are
    themselves part of what is being checked.
    """
    if line_ends:
        text = text.replace("\r\n", "\n")
    for needle, label in replacements:
        text = text.replace(needle, label)
        # A path inside a JSON string has each backslash written twice.
        text = text.replace(needle.replace("\\", "\\\\"), label)
    return _LABELLED_PATH.sub(
        lambda m: m.group(1) + m.group(2).replace("\\\\", "/").replace("\\", "/"), text
    )


def _normalised_copy(source: Path, work: Path, replacements: list[tuple[str, str]]) -> Path:
    """A copy of a document the implementation wrote, with machine paths replaced.

    Some documents carry a path in a message (a configuration error names its file). The
    expected side holds the same labels, so the comparison does not depend on where the
    case happened to be unpacked.
    """
    text = source.read_bytes().decode("utf-8")
    target = work / "normalised" / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_normalise(text, replacements, line_ends=False).encode("utf-8"))
    return target


def _replacements(root: Path, out: Path) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for path, label in ((out, "<OUT>"), (root, "<ROOT>")):
        for candidate in {str(path), str(path.resolve())}:
            pairs.append((candidate, label))
            pairs.append((candidate.replace("\\", "/"), label))
    # Longest first, so a path that contains another is replaced as a whole.
    return sorted(pairs, key=lambda pair: -len(pair[0]))


def _expand(value: str, root: Path, out: Path) -> str:
    return value.replace("{ROOT}", str(root)).replace("{OUT}", str(out))


@dataclass
class Run:
    exit_code: int
    stdout: str
    stderr: str


def _invoke(
    command: list[str], args: list[str], cwd: Path, root: Path, out: Path
) -> Run:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "NO_COLOR": "1"}
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    expanded = [_expand(item, root, out) for item in args]
    completed = subprocess.run(
        [*command, *expanded], cwd=cwd, capture_output=True, env=env, check=False
    )
    replacements = _replacements(root, out)
    return Run(
        exit_code=completed.returncode,
        stdout=_normalise(completed.stdout.decode("utf-8", "replace"), replacements),
        stderr=_normalise(completed.stderr.decode("utf-8", "replace"), replacements),
    )


def _prepare(case_dir: Path, case: dict[str, Any], work: Path, command: list[str]) -> Path:
    """Build the working copy of one case and run its steps. Returns the case's root."""
    root = work / "root"
    _copy_tree(case_dir / "input", root)

    for rel in case.get("fake_repositories", []):
        (root / rel / ".git").mkdir(parents=True, exist_ok=True)
    for rel in case.get("git", ["."] if case.get("mode", "repo") == "repo" else []):
        _make_repository(root / rel if rel != "." else root)

    out = work / "out"
    for step in case.get("steps", []):
        if step["op"] == "overlay":
            repository = root / step.get("into", ".")
            overlay = case_dir / step.get("from", "overlay")
            _copy_tree(overlay, repository)
            if step.get("stage"):
                _git(repository, "add", "-A")
            if step.get("commit"):
                _git(repository, "add", "-A")
                _git(repository, "commit", "-q", "-m", "overlay")
        elif step["op"] == "run":
            prior = _invoke(command, step["args"], _cwd_for(case, root, work), root, out)
            if prior.exit_code not in step.get("allowed_exit_codes", [0]):
                raise RuntimeError(
                    f"a preparation run exited {prior.exit_code} (allowed "
                    f"{step.get('allowed_exit_codes', [0])})"
                )
        elif step["op"] == "write":
            target = root / step["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(step["text"], encoding="utf-8", newline="")
        else:
            raise RuntimeError(f"unknown step: {step['op']}")
    return root


def _cwd_for(case: dict[str, Any], root: Path, work: Path) -> Path:
    return root if case.get("mode", "repo") == "repo" else work


def _compare_stream(
    label: str, expected: str, actual: str, result: Result, show_details: bool
) -> None:
    if expected == actual:
        return
    result.problems.append(f"{label} differs")
    if show_details:
        diff = difflib.unified_diff(
            expected.splitlines(),
            actual.splitlines(),
            fromfile=f"expected {label}",
            tofile=f"actual {label}",
            lineterm="",
        )
        result.details.extend(list(diff)[:60])


def _compare_artifacts(
    case_dir: Path,
    case: dict[str, Any],
    work: Path,
    root: Path,
    out: Path,
    result: Result,
    show_details: bool,
) -> None:
    expected_dir = case_dir / "expected"
    for item in case.get("artifacts", []):
        actual = Path(_expand(item["actual"], root, out))
        expected = expected_dir / item["expected"]
        label = item["expected"]
        if not actual.is_file():
            result.problems.append(f"document not written: {label}")
            continue
        try:
            found = compare_index.compare_files(
                expected, _normalised_copy(actual, work, _replacements(root, out))
            )
        except (OSError, ValueError) as exc:
            result.problems.append(f"document unreadable: {label} ({type(exc).__name__})")
            continue
        if not found.same:
            result.problems.append(f"document differs: {label}")
            report = compare_index.format_report(found, show_details=show_details)
            result.details.extend(f"  {line}" for line in report.splitlines())
    for pattern in case.get("absent", []):
        if Path(_expand(pattern, root, out)).exists():
            result.problems.append(f"a document was written that must not be: {pattern}")


def run_case(
    case_dir: Path, command: list[str], *, record: bool, show_details: bool
) -> Result:
    case = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
    result = Result(case_dir.name)

    with tempfile.TemporaryDirectory(prefix=f"golden-{case_dir.name}-") as raw:
        work = Path(raw)
        try:
            root = _prepare(case_dir, case, work, command)
        except RuntimeError as exc:
            result.problems.append(f"preparation failed: {exc}")
            return result
        out = work / "out"
        actual = _invoke(command, case["args"], _cwd_for(case, root, work), root, out)

        expected_dir = case_dir / "expected"
        if record:
            expected_dir.mkdir(parents=True, exist_ok=True)
            (expected_dir / "result.json").write_text(
                json.dumps({"exit_code": actual.exit_code}, indent=2) + "\n", encoding="utf-8"
            )
            (expected_dir / "stdout.txt").write_text(actual.stdout, encoding="utf-8", newline="")
            (expected_dir / "stderr.txt").write_text(actual.stderr, encoding="utf-8", newline="")
            for item in case.get("artifacts", []):
                source = Path(_expand(item["actual"], root, out))
                target = expected_dir / item["expected"]
                target.parent.mkdir(parents=True, exist_ok=True)
                if not source.is_file():
                    result.problems.append(f"nothing to record for {item['expected']}")
                    continue
                shutil.copyfile(_normalised_copy(source, work, _replacements(root, out)), target)
            return result

        expected_exit = json.loads((expected_dir / "result.json").read_text(encoding="utf-8"))[
            "exit_code"
        ]
        if actual.exit_code != expected_exit:
            result.problems.append(f"exit status {actual.exit_code}, expected {expected_exit}")

        streams = case.get("streams", ["stdout", "stderr"])
        for name, text in (("stdout", actual.stdout), ("stderr", actual.stderr)):
            if name in streams:
                expected_text = (expected_dir / f"{name}.txt").read_text(encoding="utf-8")
                _compare_stream(
                    name, expected_text.replace("\r\n", "\n"), text, result, show_details
                )

        _compare_artifacts(case_dir, case, work, root, out, result, show_details)
    return result


def select_cases(names: list[str] | None) -> list[Path]:
    available = sorted(path for path in CASES.iterdir() if (path / "case.json").is_file())
    if not names:
        return available
    wanted = set(names)
    chosen = [path for path in available if path.name in wanted]
    missing = wanted - {path.name for path in chosen}
    if missing:
        raise SystemExit(f"run_golden: no such case: {', '.join(sorted(missing))}")
    return chosen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the omitnix golden cases.")
    parser.add_argument(
        "--cmd", required=True, help='the command to test, e.g. "python -m omitnix"'
    )
    parser.add_argument("--cases", help="comma-separated case names (default: all)")
    parser.add_argument("--list", action="store_true", help="list the cases and stop")
    parser.add_argument(
        "--record",
        action="store_true",
        help="write what the command did as the expected result. Only for the Python "
        "reference, and only when the behaviour is meant to change.",
    )
    parser.add_argument("--show-details", action="store_true")
    args = parser.parse_args(argv)

    names = args.cases.split(",") if args.cases else None
    cases = select_cases(names)
    if args.list:
        for path in cases:
            print(path.name)
        return 0

    command = shlex.split(args.cmd, posix=os.name != "nt")
    failures = 0
    for path in cases:
        result = run_case(path, command, record=args.record, show_details=args.show_details)
        if result.passed:
            print(f"ok    {result.name}")
            continue
        failures += 1
        print(f"FAIL  {result.name}")
        for problem in result.problems:
            print(f"      {problem}")
        for line in result.details:
            print(f"      {line}")

    total = len(cases)
    print(f"\n{total - failures}/{total} cases {'recorded' if args.record else 'passed'}")
    return 1 if failures else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
