import functools
import logging
import os
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import chain
from pathlib import Path

from lxml import etree

from odoo.modules import Manifest

from . import _pretty_xml, lint_case
from ._rules import Finding
from ._xml_identity import PARSER
from ._xml_rules import RULES, Context, DataFile

_logger = logging.getLogger(__name__)

DATA_ROOTS = frozenset({"odoo", "data", "openerp"})


@dataclass(frozen=True, slots=True)
class _Module:
    name: str
    root: str
    listed: frozenset[str]


@functools.cache
def _modules() -> tuple[_Module, ...]:
    out = []
    for manifest in Manifest.get_all_addon_manifests():
        root = str(Path(manifest.path))
        listed = frozenset(
            os.path.normpath(str(Path(root, rel)))
            for key in ("data", "demo")
            for rel in manifest.declared.get(key) or ()
        )
        out.append(_Module(manifest.name, root, listed))
    return tuple(sorted(out, key=lambda m: -len(m.root)))


def _module_of(path: str) -> _Module | None:
    for module in _modules():
        if path.startswith(module.root + os.sep):
            return module
    return None


@functools.cache
def _python_sources_by_module() -> dict[str, str]:
    sources: dict[str, list[str]] = {}
    for path in lint_case.module_file_paths():
        if not path.endswith(".py") or "/static/" in path:
            continue
        module = _module_of(path)
        if module is None:
            continue
        try:
            sources.setdefault(module.name, []).append(
                Path(path).read_text(encoding="utf-8")
            )
        except OSError, UnicodeDecodeError:
            continue
    return {name: "\n".join(chunks) for name, chunks in sources.items()}


def _mentioned_in_python(module: _Module, path: str) -> bool:
    relative = os.path.relpath(path, module.root)
    source = _python_sources_by_module().get(module.name, "")
    return relative in source or Path(relative).name in source


def _data_files(paths) -> tuple[DataFile, ...]:
    out = []
    for path in paths:
        module = _module_of(str(path))
        if module is None:
            continue
        try:
            tree = etree.parse(str(path), PARSER)
        except etree.XMLSyntaxError:
            continue
        root = tree.getroot()
        if root.tag not in DATA_ROOTS:
            continue
        resolved = os.path.normpath(str(path))
        out.append(
            DataFile(
                path=str(path),
                module=module.name,
                root=root,
                listed=resolved in module.listed,
                loaded_from_python=_mentioned_in_python(module, resolved),
            )
        )
    return tuple(out)


@functools.cache
def data_files() -> tuple[DataFile, ...]:
    return _data_files(lint_case.core_data_files())


@functools.cache
def sibling_data_files() -> tuple[DataFile, ...]:
    return _data_files(
        path
        for path in map(Path, lint_case.iter_module_files("*.xml"))
        if not lint_case.is_core_path(str(path)) and _pretty_xml.is_formattable(path)
    )


def repository_of(path: str) -> str:
    module = _module_of(path)
    return lint_case.repo_of(module.root if module else path)


@functools.cache
def context() -> Context:
    return Context(
        declared_models=lint_case.declared_models(),
        known_modules=frozenset(module.name for module in _modules()),
    )


def scan(
    core: Iterable[DataFile], siblings: Iterable[DataFile], ctx: Context
) -> dict[str, list[Finding]]:
    by_rule: dict[str, list[Finding]] = {rule.name: [] for rule in RULES}
    every_repository = tuple(rule for rule in RULES if rule.every_repository)
    for data_file, rules in chain(
        ((data_file, RULES) for data_file in core),
        ((data_file, every_repository) for data_file in siblings),
    ):
        for rule in rules:
            for lineno, message in rule.check(data_file, ctx):
                by_rule[rule.name].append(
                    Finding(data_file.path, lineno, rule.name, message)
                )
    return by_rule


@functools.cache
def get_findings() -> dict[str, list[Finding]]:
    by_rule = scan(data_files(), sibling_data_files(), context())
    _logger.info(
        "scanned %s XML data files and %s outside odoo, %s finding(s) across %s "
        "rule(s)",
        len(data_files()),
        len(sibling_data_files()),
        sum(map(len, by_rule.values())),
        sum(1 for found in by_rule.values() if found),
    )
    return by_rule
