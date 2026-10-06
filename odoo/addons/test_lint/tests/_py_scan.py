import ast
import functools
import io
import logging
import tokenize
from pathlib import Path

from . import (
    _checker_null_unique,
    _checker_translated_unique,
    _model_classes,
    _parallel,
    lint_case,
)
from ._rules import CROSS_UNIT_RULES, RULES, Finding, Source, is_test_path

_logger = logging.getLogger(__name__)

__all__ = [
    "CROSS_UNIT_RULES",
    "RULES",
    "Finding",
    "Source",
    "corpus",
    "cross_unit_violations",
    "findings",
    "findings_by_repository",
    "is_test_path",
    "report",
    "scan_many",
    "scan_one",
]

_NOT_OURS = ("/_vendor/", "/upgrades/", "/migrations/")


@functools.cache
def corpus() -> tuple[Source, ...]:
    # every repository on the addons path, each graded against its own floors
    seen: set[str] = set()
    sources: list[Source] = []
    for root, repo in lint_case.module_roots_by_repository():
        for dirpath, _dirnames, filenames in Path(root).walk():
            for name in filenames:
                path = str(dirpath / name)
                if not path.endswith(".py") or path in seen:
                    continue
                if any(part in path for part in _NOT_OURS):
                    continue
                seen.add(path)
                sources.append(Source(path, in_module=True, repo=repo))
    for path in lint_case.framework_paths():
        if any(part in path for part in _NOT_OURS):
            continue
        if path not in seen:
            seen.add(path)
            sources.append(Source(path, in_module=False))
    return tuple(sorted(sources, key=lambda s: s.path))


@functools.cache
def _repository_of_path() -> dict[str, str]:
    return {source.path: source.repo for source in corpus()}


def findings_by_repository(rule: str) -> dict[str, list[Finding]]:
    repos = _repository_of_path()
    by_repo: dict[str, list[Finding]] = {}
    for finding in findings().get(rule, []):
        by_repo.setdefault(repos.get(finding.path, "odoo"), []).append(finding)
    return by_repo


type Row = tuple[str, str, int, int, str]


# What the Python scan still reads per file: whether it parses and tokenises at
# all, and the model classes the two cross-unit rules fold. The per-file rules
# are the ruff fork's.
@functools.cache
def scan_one(path: str) -> tuple[list[Row], list[_model_classes.ModelClass]]:
    try:
        raw = Path(path).read_bytes()
        tree = ast.parse(raw, path)
    except (OSError, SyntaxError, ValueError) as exc:
        return [("unreadable-source", path, 1, 0, f"{type(exc).__name__}: {exc}")], []
    source = io.StringIO(raw.decode("utf-8", errors="replace"))
    try:
        for _token in tokenize.generate_tokens(source.readline):
            pass
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError) as exc:
        return [("unreadable-source", path, 1, 0, f"{type(exc).__name__}: {exc}")], []
    return [], _model_classes.collect(tree)


def scan_many(paths: list[str]) -> tuple[list[Row], list]:
    rows: list[Row] = []
    units: list = []
    for path in paths:
        file_rows, classes = scan_one(path)
        rows.extend(file_rows)
        if classes:
            units.append((path, classes))
    return rows, units


@functools.cache
def _scan() -> tuple[list[Row], list, int]:
    paths = [source.path for source in corpus()]

    parts, jobs = _parallel.map_chunks(scan_many, paths)
    rows = [row for part_rows, _units in parts for row in part_rows]
    units = [unit for _rows, part_units in parts for unit in part_units]
    return rows, units, jobs


def cross_unit_violations(units: list, repo_of) -> list:
    # a repository's models are judged against the declarations it builds on,
    # so an extension in a later repository never settles an earlier one's key
    found = []
    for repo in sorted({repo_of(path) for path, _classes in units}):
        layer = set(lint_case.visible(repo))
        seen = [(path, cls) for path, cls in units if repo_of(path) in layer]
        found += [
            violation
            for violation in (
                *_checker_translated_unique.violations(seen),
                *_checker_null_unique.violations(seen),
            )
            if repo_of(violation.path) == repo
        ]
    return found


@functools.cache
def findings() -> dict[str, list[Finding]]:
    rows, units, jobs = _scan()

    by_rule: dict[str, list[Finding]] = {}
    for rule, path, lineno, col, message in rows:
        by_rule.setdefault(rule, []).append(Finding(path, lineno, rule, message, col))

    repos = _repository_of_path()
    cross = cross_unit_violations(units, lambda path: repos.get(path, "odoo"))
    for violation in cross:
        if is_test_path(violation.path):
            continue
        by_rule.setdefault(violation.rule, []).append(
            Finding(violation.path, violation.lineno, violation.rule, str(violation))
        )

    _logger.info(
        "scanned %s Python files in %s process(es), %s finding(s) across %s rule(s)",
        len(corpus()),
        jobs,
        sum(map(len, by_rule.values())),
        len(by_rule),
    )
    return by_rule


def model_class_scale() -> tuple[int, int]:
    # how many model classes and constraints the unique-constraint checkers read
    _rows, units, _jobs = _scan()
    return (
        sum(len(classes) for _path, classes in units),
        sum(len(cls.constraints) for _path, classes in units for cls in classes),
    )


def report(rule: str, header: str) -> str:
    found = sorted(findings().get(rule, []), key=lambda f: f.sort_key)
    if not found:
        return ""
    return f"{len(found)} {header}:\n  " + "\n  ".join(map(str, found))
