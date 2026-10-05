"""Read-only probes on public synthetic inputs; no product patches or fixture execution."""
from __future__ import annotations

import argparse
import ast
import importlib.metadata
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

import sqlglot
from sqlglot import exp

from omitnix.adapters import go, php, python, rust, tsjs
from omitnix.adapters._extract import sql_candidates, sql_text
from omitnix.adapters._sql import looks_like_sql, read_sql
from omitnix.adapters._treesitter import load_grammar, text_of


def parse_view(sql: str, dialect: str | None) -> dict:
    try:
        statements = sqlglot.parse(sql, read=dialect)
        return {
            "parsed": True,
            "statements": [
                {
                    "type": type(statement).__name__,
                    "tables": [
                        {"name": table.name, "parent_type": type(table.parent).__name__}
                        for table in statement.find_all(exp.Table)
                    ],
                }
                for statement in statements if statement is not None
            ],
        }
    except Exception as error:  # noqa: BLE001 - diagnostic records parser failures
        return {
            "parsed": False, "error_type": type(error).__name__,
            "error_first_line": str(error).splitlines()[0],
        }


def view(sql: str) -> dict:
    return {
        "sql": sql, "gate": looks_like_sql(sql), "wrapper": asdict(read_sql(sql)),
        "sqlglot": {
            str(dialect): parse_view(sql, dialect)
            for dialect in (None, "mysql", "sqlite", "postgres")
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[4]
    output = args.output.resolve()
    if output == repo or repo in output.parents:
        parser.error("--output must be outside the repository")
    logging.getLogger("sqlglot").setLevel(logging.ERROR)
    root = repo / "rewrite/truth/synthetic/corpus"
    answers = json.loads((root.parent / "answers.json").read_text(encoding="utf-8"))
    categories = {"ddl", "dialect", "write", "unsupported", "escape", "comment"}
    selected = [entry for entry in answers["files"] if entry["category"] in categories]
    modules = {"php": php, "python": python, "ts": tsjs, "go": go, "rust": rust}
    files = []
    for entry in selected:
        source = (root / entry["file"]).read_text(encoding="utf-8")
        record = {
            "file": entry["file"], "category": entry["category"],
            "source": source, "candidates": [],
        }
        if entry["lang"] == "sql":
            record["whole_file"] = view(source)
            if entry["category"] == "ddl":
                record["statements"] = [view(sql) for sql in source.split(";") if sql.strip()]
            if entry["category"] == "unsupported":
                # Diagnostic copies only: neither transformation is a proposed script parser.
                record["diagnostics"] = {
                    "client_directives_removed": view(
                        "\n".join(source.splitlines()[1:5]).replace("END //", "END;")
                    ),
                    "body_only": view(source.splitlines()[3]),
                }
            files.append(record)
            continue
        module = modules[entry["lang"]]
        if module == tsjs:
            grammar = load_grammar(*tsjs.GRAMMARS[".ts"], tsjs.QUERY_NAME, extra=tsjs.EXTRA)
        else:
            grammar = load_grammar(
                module.GRAMMAR_NAME, module.GRAMMAR_MODULE,
                module.GRAMMAR_SYMBOL, extra=module.EXTRA,
            )
        parsed = grammar.parse(source.encode("utf-8"))
        record["host_parse_has_error"] = parsed.has_error
        candidates = (
            php._sql_candidates(parsed) if module == php
            else sql_candidates(parsed, module.SHAPE)
        )
        for node in candidates:
            sql, dynamic = (
                php._sql_text(node) if module == php else sql_text(node, module.SHAPE)
            )
            candidate = {
                "source_line": node.start_point.row + 1, "node_type": node.type,
                "literal_source": text_of(node), "dynamic": dynamic, "extracted": view(sql),
            }
            if entry["category"] == "escape":
                # Valid for these simple synthetic quote-escape specimens only.
                # This is NOT a PHP/JS decoder or a proposed production implementation.
                candidate["semantic_literal_value"] = view(ast.literal_eval(text_of(node)))
            if entry["case"] == "php06_heredoc_comment":
                body = next(child for child in node.named_children if child.type == "heredoc_body")
                candidate["verbatim_heredoc_body"] = view(text_of(body))
            if entry["case"] == "rs03_write" and "?1" in sql:
                candidate["altered_parameter_diagnostic"] = view(sql.replace("?1", "?"))
            record["candidates"].append(candidate)
        files.append(record)
    packages = [
        "sqlglot", "tree-sitter", "tree-sitter-php", "tree-sitter-python",
        "tree-sitter-typescript", "tree-sitter-go", "tree-sitter-rust",
    ]
    result = {
        "python": sys.version.split()[0],
        "packages": {name: importlib.metadata.version(name) for name in packages},
        "method": (
            "Unchanged source/product. Existing helpers are called directly. "
            "Semantic literal and verbatim body values concern these exact fixtures. "
            "Other transformed diagnostics are labeled; none is an end-to-end score."
        ),
        "quoted_placeholder_probe": {
            sql: asdict(read_sql(sql)) for sql in (
                "SELECT * FROM ` omitnix_placeholder `",
                "SELECT * FROM `omitnix_placeholder`",
                "SELECT * FROM omitnix_placeholder",
            )
        },
        "files": files,
    }
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Probed {len(files)} public source files; output outside repository.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
