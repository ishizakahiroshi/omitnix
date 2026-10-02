# ruff: noqa: E501
"""Build the inputs of the golden cases in ``rewrite/golden/cases/``.

Only the inputs and ``case.json`` are written here. What the reference does with them is
recorded afterwards, by the Python version:

    python rewrite/tools/make_cases.py
    python rewrite/tools/run_golden.py --cmd "python -m omitnix" --record

Every file is either copied from ``tests/fixtures`` (invented code for an invented
service: orders, customers, search_index, audit_log) or written here from invented text.
Nothing in a case may name a real system, and a case that needs a real repository to make
its point does not belong in this directory.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
GOLDEN = HERE.parent / "golden"
CASES = GOLDEN / "cases"
FIXTURES = HERE.parent.parent / "tests" / "fixtures"

ROOT_ARGS = ["--root", "{ROOT}"]
INDEX = {"actual": "{ROOT}/.omitnix/index.json", "expected": "index.json"}
AUTH_CONFIG = """authentication_functions:
  - require_session
authorization_functions:
  - apply_visibility_filter
"""

Content = str | bytes


def fx(rel: str) -> bytes:
    return (FIXTURES / rel).read_bytes()


def fixtures(prefix: str, directory: str, *, skip: tuple[str, ...] = ()) -> dict[str, Content]:
    """Every file under ``tests/fixtures/<directory>``, placed under ``<prefix>/``."""
    base = FIXTURES / directory
    return {
        f"{prefix}/{path.relative_to(base).as_posix()}": path.read_bytes()
        for path in sorted(base.rglob("*"))
        if path.is_file() and path.relative_to(base).as_posix() not in skip
    }


def _write(directory: Path, files: dict[str, Content]) -> None:
    for rel, content in files.items():
        target = directory / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        data = content.encode("utf-8") if isinstance(content, str) else content
        target.write_bytes(data)


def add(
    name: str,
    description: str,
    *,
    files: dict[str, Content] | None = None,
    overlay: dict[str, Content] | None = None,
    args: list[str] | None = None,
    steps: list[dict[str, Any]] | None = None,
    artifacts: list[dict[str, str]] | None = None,
    absent: list[str] | None = None,
    mode: str = "repo",
    git: list[str] | None = None,
    fake_repositories: list[str] | None = None,
    streams: list[str] | None = None,
) -> None:
    directory = CASES / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "input").mkdir(exist_ok=True)
    _write(directory / "input", files or {})
    if overlay:
        _write(directory / "overlay", overlay)

    case: dict[str, Any] = {
        "description": description,
        "mode": mode,
        "args": args if args is not None else list(ROOT_ARGS),
    }
    if git is not None:
        case["git"] = git
    if fake_repositories:
        case["fake_repositories"] = fake_repositories
    if steps:
        case["steps"] = steps
    case["artifacts"] = [INDEX] if artifacts is None and mode == "repo" else (artifacts or [])
    if absent:
        case["absent"] = absent
    if streams is not None:
        case["streams"] = streams
    (directory / "case.json").write_text(
        json.dumps(case, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


# --- shared pieces ------------------------------------------------------------------

PHP_FILES = fixtures("src", "php", skip=())
PHP_CONFIG = "include:\n  - '**/*.php'\n" + AUTH_CONFIG
SRC_FILES: dict[str, Content] = {}
for _directory, _prefix in (
    ("python", "src/python"),
    ("go", "src/go"),
    ("rust", "src/rust"),
    ("tsjs", "src/tsjs"),
    ("html", "src/html"),
    ("sql", "src/sql"),
    ("minimal", "src/minimal"),
):
    SRC_FILES.update(fixtures(_prefix, _directory))
SRC_FILES.update(fixtures("src/php", "php"))


def build() -> None:
    # Rebuild inputs from scratch, but keep ``expected/``: that is what the reference
    # recorded, and only ``run_golden.py --record`` is allowed to change it.
    CASES.mkdir(parents=True, exist_ok=True)
    for directory in CASES.iterdir():
        for child in directory.iterdir():
            if child.name == "expected":
                continue
            shutil.rmtree(child) if child.is_dir() else child.unlink()

    # --- one adapter at a time ------------------------------------------------------
    add("c01_php", "PHP: summary, calls, SQL, one hop, a refused syntax error.",
        files={".omitnix.yaml": PHP_CONFIG, **PHP_FILES})
    add("c02_php_fail_on_unknown", "fail_on_unknown turns the unreadable PHP file into exit 1.",
        files={".omitnix.yaml": PHP_CONFIG + "fail_on_unknown: true\n", **PHP_FILES})
    add("c03_php_schema", "A schema snapshot: tables with no reference, and one not in it.",
        files={".omitnix.yaml": PHP_CONFIG + "schema_snapshot: src/schema.json\n", **PHP_FILES})
    add("c04_php_hop_outside_scan", "A required file that the configuration excludes is not followed.",
        files={".omitnix.yaml": PHP_CONFIG + "exclude:\n  - 'src/common/**'\n", **PHP_FILES})
    for name, directory, config in (
        ("c05_python", "python", AUTH_CONFIG),
        ("c06_go", "go", AUTH_CONFIG),
        ("c07_rust", "rust", AUTH_CONFIG),
        ("c08_tsjs", "tsjs", AUTH_CONFIG),
        ("c09_html", "html", ""),
        ("c10_sql", "sql", ""),
        ("c11_minimal", "minimal", ""),
    ):
        add(name, f"The {directory} adapter over its fixtures.",
            files={".omitnix.yaml": config, **fixtures("src", directory)} if config
            else fixtures("src", directory))

    # --- everything together, and the awkward files ---------------------------------
    mixed: dict[str, Content] = {
        ".omitnix.yaml": AUTH_CONFIG + "adapters:\n  .inc: php\n",
        **SRC_FILES,
        "docs/README.md": "# A fictional service\n",
        "data/orders.json": '{"orders": []}\n',
        "assets/logo.png": b"\x89PNG\r\n\x1a\n",
        "LICENSE": "Example licence text.\n",
        ".gitignore": "__pycache__/\n",
        "src/legacy.inc": fx("php/reindex.php"),
        "src/binary.py": b"\xff\xfe\x00 not text",
        "src/bom.php": b"\xef\xbb\xbf" + fx("php/reindex.php"),
        "src/注文_list.py": '"""List orders (a non-ASCII file name)."""\n',
        "src/with space.py": '"""A file name with a space."""\n',
        "vendor/lib/skipped.php": fx("php/reindex.php"),
        "node_modules/pkg/index.js": "module.exports = 1;\n",
        "dist/bundle.js": "var a = 1;\n",
        "Makefile": "all:\n\techo done\n",
    }
    add("c12_mixed", "All adapters, unclaimed files, a binary .py, a BOM, an override, "
        "non-ASCII and spaced names, default exclusions.", files=mixed)
    add("c13_no_config", "No .omitnix.yaml: authentication and authorization are not_configured.",
        files={**PHP_FILES, "vendor/skipped.php": fx("php/reindex.php"),
               **fixtures("src/py", "python")})

    # --- configuration --------------------------------------------------------------
    one_php = {"a.php": fx("php/reindex.php")}
    for name, description, config in (
        ("c14_config_unknown_key", "An unknown key is an error, exit 2.", "incldue:\n  - '**/*.php'\n"),
        ("c15_config_wrong_type", "A key of the wrong type is an error, exit 2.", "fail_on_unknown: maybe\n"),
        ("c16_config_extension_without_dot", "An adapters key without a dot is an error.", "adapters:\n  inc: php\n"),
        ("c17_config_unknown_adapter", "An adapters value naming no adapter is an error.", "adapters:\n  .inc: cobol\n"),
        ("c18_config_exemption_without_reason", "A gate exemption needs a reason, exit 2.",
         "gate_exemptions:\n  - paths: ['src/**']\n    skip: [authorization]\n"),
        ("c19_config_missing_schema_snapshot", "A schema_snapshot that does not exist is an error.",
         "schema_snapshot: nope.json\n"),
    ):
        add(name, description, files={".omitnix.yaml": config, **one_php}, artifacts=[],
            absent=["{ROOT}/.omitnix/index.json"])
    add("c20_exclude_defaults_false", "exclude_defaults: false walks vendor/ and node_modules/.",
        files={".omitnix.yaml": "exclude_defaults: false\nexclude:\n  - '**/skipme/**'\n",
               "vendor/a.php": fx("php/reindex.php"), "node_modules/b.js": "var b = 1;\n",
               "skipme/c.php": fx("php/reindex.php"), "d.php": fx("php/reindex.php")})
    add("c21_output_dir", "output_dir moves the index, and the index is not discovered.",
        files={".omitnix.yaml": "output_dir: out/inventory\n", "a.php": fx("php/reindex.php")},
        artifacts=[{"actual": "{ROOT}/out/inventory/index.json", "expected": "index.json"}])
    glob_files = {
        path: "x\n"
        for path in (
            "api/orders.dat", "orders.dat", "api/nested/orders.dat", "api/nested/deep/orders.dat",
            "vendor/lib/thing.dat", "app/vendor/lib/thing.dat", "app/vendored/thing.dat",
            "web/node_modules/pkg/index.dat", "report_1.dat", "report_7.dat", "report_a.dat",
            "report_10.dat", "build/a.dat", "build/sub/b.dat", "build/sub/deep/c.dat",
            "src/keep/a.dat", "src/keep/a.txt",
        )
    }
    add("c22_globs", "include and exclude patterns: *, **, ?, [0-9], [!0-9], direct children only.",
        files={".omitnix.yaml": "include:\n  - '**/*.dat'\nexclude:\n  - 'api/*.dat'\n"
               "  - 'report_[!0-9].dat'\n  - 'report_?.dat'\n  - 'build/*'\n  - 'app/vendored/**'\n",
               **glob_files})

    # --- discovery modes ------------------------------------------------------------
    base = {".omitnix.yaml": PHP_CONFIG, "src/a.php": fx("php/reindex.php")}
    untracked = {"src/untracked.php": fx("php/notes.php"), "src/scratch/tmp.php": fx("php/notes.php")}
    add("c23_tracked_only_ignores_untracked", "The default asks git: an untracked file is not seen.",
        files=base, overlay=untracked, steps=[{"op": "overlay"}])
    add("c24_all_files_walks", "--all-files walks the tree: untracked files are seen.",
        files=base, overlay=untracked, steps=[{"op": "overlay"}],
        args=[*ROOT_ARGS, "--all-files"])
    add("c25_no_git_falls_back_to_a_walk", "Without git the tree is walked and the note is said.",
        files=base, git=[])
    add("c26_staged_file_is_tracked", "A staged addition is part of the tracked set.",
        files=base, overlay=untracked, steps=[{"op": "overlay", "stage": True}])

    # --- partial runs, print, check -------------------------------------------------
    two = [*ROOT_ARGS, "--files", "src/orders_list.php", "src/reindex.php"]
    add("c27_files_does_not_write", "--files analyzes a subset and does not touch the index.",
        files={".omitnix.yaml": PHP_CONFIG, **PHP_FILES}, args=two, artifacts=[],
        absent=["{ROOT}/.omitnix/index.json"])
    add("c28_files_write", "--files --write writes a partial document.",
        files={".omitnix.yaml": PHP_CONFIG, **PHP_FILES}, args=[*two, "--write"])
    add("c29_files_excluded_and_missing", "A requested path the configuration excludes is counted.",
        files={".omitnix.yaml": PHP_CONFIG + "exclude:\n  - 'src/common/**'\n", **PHP_FILES},
        args=[*ROOT_ARGS, "--files", "src/reindex.php", "src/common/queries.php", "src/nope.php"],
        artifacts=[], absent=["{ROOT}/.omitnix/index.json"])
    php_repo = {".omitnix.yaml": PHP_CONFIG, **PHP_FILES}
    for name, target, config in (
        ("c30_print_analyzed", "src/orders_list.php", PHP_CONFIG),
        ("c31_print_unresolved", "src/export.php", PHP_CONFIG),
        ("c32_print_unknown", "src/broken.php", PHP_CONFIG),
        ("c33_print_unknown_fails_when_asked", "src/broken.php", PHP_CONFIG + "fail_on_unknown: true\n"),
        ("c34_print_unclaimed", "src/schema.json", AUTH_CONFIG),
        ("c35_print_missing_file", "src/absent.php", PHP_CONFIG),
        ("c36_print_outside_root", "../elsewhere.php", PHP_CONFIG),
    ):
        add(name, f"--print {target}.", files={**php_repo, ".omitnix.yaml": config},
            args=[*ROOT_ARGS, "--print", target], artifacts=[])
    check_files = {".omitnix.yaml": PHP_CONFIG, **PHP_FILES}
    write_index = {"op": "run", "args": list(ROOT_ARGS)}
    add("c37_check_current", "--check on a current document is quiet and exits 0.",
        files=check_files, steps=[write_index], args=[*ROOT_ARGS, "--check"], artifacts=[])
    add("c38_check_stale_after_a_new_file", "--check says what changed and exits 3.",
        files=check_files, overlay={"src/added.php": fx("php/notes.php")},
        steps=[write_index, {"op": "overlay", "stage": True}],
        args=[*ROOT_ARGS, "--check"], artifacts=[])
    add("c39_check_nothing_generated", "--check with no document exits 3.",
        files=check_files, args=[*ROOT_ARGS, "--check"], artifacts=[])
    add("c40_check_current_but_unknown_fails", "A current document, an unreadable file, "
        "fail_on_unknown: exit 1.",
        files={**check_files, ".omitnix.yaml": PHP_CONFIG + "fail_on_unknown: true\n"},
        steps=[{**write_index, "allowed_exit_codes": [0, 1]}], args=[*ROOT_ARGS, "--check"],
        artifacts=[])
    add("c41_check_discovery_mode_changed", "A document made with --all-files, checked without.",
        files=check_files, overlay={"src/untracked.php": fx("php/notes.php")},
        steps=[{"op": "overlay"}, {"op": "run", "args": [*ROOT_ARGS, "--all-files"]}],
        args=[*ROOT_ARGS, "--check"], artifacts=[])

    # --- usage errors ---------------------------------------------------------------
    small = {".omitnix.yaml": "", "a.php": fx("php/reindex.php")}
    for name, extra in (
        ("c42_gate_with_check", ["--gate", "--check"]),
        ("c43_gate_with_write", ["--gate", "--write"]),
        ("c44_since_without_gate", ["--since", "base"]),
        ("c45_all_files_with_gate", ["--gate", "--all-files"]),
        ("c46_workspace_only_flag_alone", ["--jobs", "2"]),
        ("c47_workspace_only_out_alone", ["--out", "{OUT}"]),
        ("c48_unknown_flag", ["--nonsense"]),
    ):
        # An unknown flag is rejected by the argument parser, whose wording belongs to the
        # implementation. Only the exit status is part of the contract there.
        add(name, f"Usage: {' '.join(extra)}.", files=small, args=[*ROOT_ARGS, *extra],
            artifacts=[], streams=[] if name == "c48_unknown_flag" else None)
    add("c49_help", "--help exits 0. The wording of the usage text is not compared.",
        files=small, args=["--help"], artifacts=[], streams=[])
    add("c50_version", "--version prints the tool name and version.", files=small,
        args=["--version"], artifacts=[], streams=["stdout"])

    # --- the gate -------------------------------------------------------------------
    gate_base = {".omitnix.yaml": AUTH_CONFIG, "src/old.py": '"""An existing module."""\n'}
    good = (
        '"""Show one order to its owner."""\n\n'
        "def show(order_id):\n    require_session()\n    apply_visibility_filter(order_id)\n"
        "    return order_id\n"
    )
    bad_overlay = {
        "src/new_report.php": "<?php\nfunction report() { return 1; }\n",
        "src/new_broken.php": fx("php/broken.php"),
        "docs/notes.md": "# Notes\n",
        "src/dynamic.py": '"""Build a query."""\n\ndef f(t):\n    require_session()\n'
        '    apply_visibility_filter(t)\n    cur.execute("SELECT id FROM " + t)\n',
    }
    gate = [*ROOT_ARGS, "--gate"]
    add("g01_gate_passes", "A new file with a summary and both calls passes.",
        files=gate_base, overlay={"src/ok.py": good}, steps=[{"op": "overlay"}], args=gate,
        artifacts=[])
    add("g02_gate_refuses", "Missing summary and calls, an unreadable file; notices for the rest.",
        files=gate_base, overlay=bad_overlay, steps=[{"op": "overlay"}], args=gate, artifacts=[])
    add("g03_gate_staged", "The same files staged: the same answer.",
        files=gate_base, overlay=bad_overlay, steps=[{"op": "overlay", "stage": True}], args=gate,
        artifacts=[])
    add("g04_gate_since", "--since asks what the branch added, whether or not it is committed.",
        files=gate_base, overlay=bad_overlay, steps=[{"op": "overlay", "commit": True}],
        args=[*gate, "--since", "base"], artifacts=[])
    add("g05_gate_since_bad_ref", "--since with a ref git cannot resolve: exit 2, not a pass.",
        files=gate_base, overlay=bad_overlay, steps=[{"op": "overlay", "commit": True}],
        args=[*gate, "--since", "no-such-ref"], artifacts=[])
    add("g06_gate_exemption", "A configured exemption skips one check and says so.",
        files={**gate_base, ".omitnix.yaml": AUTH_CONFIG + "gate_exemptions:\n"
               "  - paths: ['src/legacy/**']\n    skip: [authorization]\n"
               "    reason: handled by the router in front of it\n"},
        overlay={"src/legacy/menu.py": '"""Menu."""\n\ndef f():\n    require_session()\n'},
        steps=[{"op": "overlay"}], args=gate, artifacts=[])
    add("g07_gate_unconfigured", "No function names configured: the check is said not to have been made.",
        files={".omitnix.yaml": "", "src/old.py": '"""An existing module."""\n'},
        overlay={"src/new.py": '"""A new module."""\n'}, steps=[{"op": "overlay"}], args=gate,
        artifacts=[])
    add("g08_gate_files_intersection", "--files narrows the gate to the new files among them.",
        files=gate_base, overlay=bad_overlay, steps=[{"op": "overlay"}],
        args=[*gate, "--files", "src/new_report.php", "src/old.py", "src/absent.py"], artifacts=[])
    add("g09_gate_excluded_by_config", "A new file the configuration excludes is counted, not gated.",
        files={**gate_base, ".omitnix.yaml": AUTH_CONFIG + "exclude:\n  - 'gen/**'\n"},
        overlay={"gen/out.php": "<?php\n"}, steps=[{"op": "overlay"}], args=gate, artifacts=[])
    add("g10_gate_no_git", "Not a git working tree: the gate cannot answer, exit 2.",
        files=gate_base, git=[], args=gate, artifacts=[])
    add("g11_gate_nothing_new", "Nothing is new: the gate passes and says what it asked.",
        files=gate_base, args=gate, artifacts=[])

    # --- workspace ------------------------------------------------------------------
    alpha = {
        "alpha/.omitnix.yaml": AUTH_CONFIG + "schema_snapshot: schema.json\n",
        "alpha/schema.json": fx("php/schema.json"),
        **fixtures("alpha/src", "php"),
        **fixtures("alpha/web", "html"),
    }
    beta = {
        "beta/README.md": "# Beta\n",
        "beta/config.json": "{}\n",
        "beta/vendor/lib/x.php": fx("php/reindex.php"),
        **fixtures("beta/app", "python"),
        **fixtures("beta/app", "sql"),
    }
    gamma = {**fixtures("gamma/pkg", "go"), **fixtures("gamma/pkg", "rust")}
    borrowed = {"study/borrowed/a.py": '"""Borrowed."""\n', "study/cloned/b.py": '"""Cloned."""\n'}
    workspace = {**{f"public/{k}": v for k, v in alpha.items()},
                 **{f"private/{k}": v for k, v in beta.items()},
                 **gamma, **borrowed}
    ws = ["--workspace", "{ROOT}", "--out", "{OUT}"]
    index_of = {
        "public/alpha": "repos/public/alpha/index.json",
        "private/beta": "repos/private/beta/index.json",
        "gamma": "repos/gamma/index.json",
    }

    def ws_artifacts(*names: str) -> list[dict[str, str]]:
        return [{"actual": "{OUT}/workspace.json", "expected": "workspace.json"}] + [
            {"actual": f"{{OUT}}/{index_of[name]}", "expected": index_of[name]} for name in names
        ]

    add("w01_workspace", "Three repositories (one with its own configuration, one with no commits), "
        "two excluded by request.", mode="workspace", files=workspace,
        git=["public/alpha", "private/beta"], fake_repositories=["gamma", "study/borrowed", "study/cloned"],
        args=[*ws, "--exclude-repo", "study"], artifacts=ws_artifacts("public/alpha", "private/beta", "gamma"))
    add("w02_workspace_dry_run", "--dry-run lists the repositories and writes nothing.",
        mode="workspace", files=workspace, git=["public/alpha", "private/beta"],
        fake_repositories=["gamma", "study/borrowed", "study/cloned"],
        args=[*ws, "--dry-run", "--exclude-repo", "study/*"], artifacts=[])
    add("w03_workspace_no_workspace_excludes", "--no-workspace-excludes discovers prose and data too.",
        mode="workspace", files=workspace, git=["public/alpha", "private/beta"],
        fake_repositories=["gamma", "study/borrowed", "study/cloned"],
        args=[*ws, "--exclude-repo", "study", "--no-workspace-excludes"],
        artifacts=ws_artifacts())
    add("w04_workspace_write_per_repo", "--write-per-repo writes .omitnix/ inside each repository.",
        mode="workspace", files=workspace, git=["public/alpha", "private/beta"],
        fake_repositories=["gamma", "study/borrowed", "study/cloned"],
        args=[*ws, "--exclude-repo", "study", "--write-per-repo"],
        artifacts=[*ws_artifacts(),
                   {"actual": "{ROOT}/public/alpha/.omitnix/index.json", "expected": "alpha.index.json"},
                   {"actual": "{ROOT}/private/beta/.omitnix/index.json", "expected": "beta.index.json"}])
    add("w05_workspace_jobs", "--jobs 2 gives the same documents as one worker.",
        mode="workspace", files=workspace, git=["public/alpha", "private/beta"],
        fake_repositories=["gamma", "study/borrowed", "study/cloned"],
        args=[*ws, "--exclude-repo", "study", "--jobs", "2"],
        artifacts=ws_artifacts("public/alpha", "private/beta", "gamma"))
    add("w06_workspace_all_files", "--all-files walks each repository.",
        mode="workspace", files=workspace, overlay={"public/alpha/src/untracked.php": fx("php/notes.php")},
        steps=[{"op": "overlay"}], git=["public/alpha", "private/beta"],
        fake_repositories=["gamma", "study/borrowed", "study/cloned"],
        args=[*ws, "--exclude-repo", "study", "--all-files"], artifacts=ws_artifacts())
    add("w07_workspace_repo_that_cannot_run", "A repository with a bad configuration is reported "
        "and does not end the survey; exit 2.", mode="workspace",
        files={"good/a.py": '"""Good."""\n', "bad/.omitnix.yaml": "nonsense: 1\n", "bad/b.py": "x = 1\n"},
        git=["good", "bad"], args=ws, artifacts=ws_artifacts())
    add("w08_workspace_unknown_exit", "An unreadable file in any repository: exit 1.",
        mode="workspace", files={"one/a.php": fx("php/broken.php"), "one/b.php": fx("php/reindex.php")},
        git=["one"], args=ws, artifacts=ws_artifacts())
    add("w09_workspace_nested_repository", "A working tree inside a working tree is not a second "
        "repository.", mode="workspace",
        files={"outer/a.py": '"""Outer."""\n', "outer/deploy/b.py": '"""Deploy clone."""\n'},
        git=["outer"], fake_repositories=["outer/deploy"], args=ws, artifacts=ws_artifacts())
    add("w10_workspace_flag_conflicts", "--workspace with --check is an error, exit 2.",
        mode="workspace", files={"one/a.py": '"""One."""\n'}, git=["one"],
        args=[*ws, "--check"], artifacts=[])
    add("w11_workspace_missing_directory", "A workspace directory that does not exist is an error.",
        mode="workspace", files={}, args=["--workspace", "{ROOT}/nowhere", "--out", "{OUT}"],
        artifacts=[])

    # A case that was renamed or dropped leaves only its old ``expected/`` behind.
    for directory in CASES.iterdir():
        if not (directory / "case.json").is_file():
            shutil.rmtree(directory)


def build_data() -> None:
    """Tables a rewrite has to carry, written out of the Python version so they cannot drift.

    ``rewrite/golden/data/`` holds nothing a rewrite should type by hand: the two
    exclusion lists (copied from ``omitnix/config.py`` and ``omitnix/workspace.py``), the
    adapters the Python version discovers (name, extensions, capabilities) and every
    reason code any adapter can emit.
    """
    from omitnix import reasons
    from omitnix.adapters import html, rust
    from omitnix.config import DEFAULT_EXCLUDE
    from omitnix.registry import build_adapter_set
    from omitnix.workspace import WORKSPACE_DEFAULT_EXCLUDE

    data = GOLDEN / "data"
    if data.exists():
        shutil.rmtree(data)
    data.mkdir(parents=True)
    (data / "default_exclude.txt").write_text("\n".join(DEFAULT_EXCLUDE) + "\n", encoding="utf-8")
    (data / "workspace_default_exclude.txt").write_text(
        "\n".join(WORKSPACE_DEFAULT_EXCLUDE) + "\n", encoding="utf-8"
    )
    adapters = [adapter.to_json() for adapter in build_adapter_set().info()]
    (data / "adapters.json").write_text(
        json.dumps(adapters, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    codes = {
        "shared": {
            name: getattr(reasons, name)
            for name in sorted(reasons.__all__)
            if name.isupper() and name != "NOT_A_TABLE_GAP"
        },
        "not_a_table_gap": sorted(reasons.NOT_A_TABLE_GAP),
        "adapter_own": {
            "html.SCRIPT_UNREADABLE": html.SCRIPT_UNREADABLE,
            "html.UNESCAPED_TEXT": html.UNESCAPED_TEXT,
            "rust.QUERY_BUILDER": rust.QUERY_BUILDER,
        },
    }
    (data / "reason_codes.json").write_text(
        json.dumps(codes, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    build()
    build_data()
    print(f"wrote {len(list(CASES.iterdir()))} cases to {CASES}")
