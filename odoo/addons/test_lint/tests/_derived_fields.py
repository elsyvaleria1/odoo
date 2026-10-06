"""Derived fields that show what their sources hide.

A related field, a stored compute and a `compute_sudo` compute are evaluated
without the reader's field access to their sources: whoever may read the
derived field reads a function of the sources. That is intended for a presence
dot, a count, "a credential is set", and a leak otherwise. A derived field
either carries an access of its own (`groups=` or `classification=`), or says
it discloses its sources on purpose (`discloses="<class>"`). This scans the
source, the way the access index does, and names the derived fields that do
neither while some dependency path crosses a field that has an access.
"""

import ast
import functools
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path

from . import _access_index as index
from . import _parallel, lint_case
from ._rules import is_test_path


@dataclass(frozen=True)
class Declared:
    access: bool = False
    discloses: bool = False
    related: str | None = None
    compute: str | None = None
    store: bool | None = None
    compute_sudo: bool | None = None


def _declared(call: ast.Call) -> Declared | None:
    func = call.func
    if not (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "fields"
        and func.attr[:1].isupper()
    ):
        return None
    values = {}
    for keyword in call.keywords:
        if keyword.arg in ("groups", "classification"):
            values["access"] = True
        elif keyword.arg == "discloses":
            values["discloses"] = True
        elif keyword.arg in ("related", "compute"):
            text = index._string(keyword.value)
            if text is None and isinstance(keyword.value, ast.Name):
                text = keyword.value.id
            values[keyword.arg] = text
        elif keyword.arg in ("store", "compute_sudo") and isinstance(
            keyword.value, ast.Constant
        ):
            values[keyword.arg] = bool(keyword.value.value)
    return Declared(**values)


def _depends_of(function: ast.FunctionDef) -> list[str]:
    paths: list[str] = []
    for decorator in function.decorator_list:
        if (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "depends"
        ):
            paths.extend(text for arg in decorator.args if (text := index._string(arg)))
    return paths


def _paths() -> list[Path]:
    found = []
    for manifest in index._module_manifests():
        if manifest.name.startswith("test_"):
            continue
        root = Path(manifest.path)
        found.extend(
            path
            for path in index._walk(root, ".py")
            if "tests" not in path.relative_to(root).parts
        )
    found.extend(
        Path(path) for path in lint_case.framework_paths() if not is_test_path(path)
    )
    return found


def _file_declarations(path: Path) -> list[tuple]:
    # in source order: ("depends", model, method, paths) and
    # ("field", model, name, declared, keywords given, line)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError, UnicodeDecodeError:
        return []
    events: list[tuple] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        model = None
        for statement in node.body:
            if isinstance(statement, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "_name" for t in statement.targets
            ):
                model = index._string(statement.value)
        if model is None:
            for statement in node.body:
                if isinstance(statement, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "_inherit"
                    for t in statement.targets
                ):
                    inherit = index._strings(statement.value)
                    model = inherit[0] if inherit else None
        if model is None:
            continue
        for statement in node.body:
            if isinstance(statement, ast.FunctionDef):
                if method_depends := _depends_of(statement):
                    events.append(
                        ("depends", model, statement.name, tuple(method_depends))
                    )
                continue
            if not (
                isinstance(statement, (ast.Assign, ast.AnnAssign))
                and isinstance(statement.value, ast.Call)
            ):
                continue
            targets = (
                statement.targets
                if isinstance(statement, ast.Assign)
                else [statement.target]
            )
            declared = _declared(statement.value)
            if declared is None:
                continue
            given = frozenset(keyword.arg for keyword in statement.value.keywords)
            events.extend(
                ("field", model, target.id, declared, given, statement.lineno)
                for target in targets
                if isinstance(target, ast.Name)
            )
    return events


@functools.cache
def _declarations(paths: tuple[Path, ...]) -> tuple[dict, dict, dict]:
    # per model: the fields its classes declare (merged, a later keyword
    # replacing an earlier one), the depends of its methods, and where each
    # field is first declared
    fields: defaultdict[str, dict[str, Declared]] = defaultdict(dict)
    depends: defaultdict[str, defaultdict[str, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
    where: dict[tuple[str, str], str] = {}
    per_file = _parallel.map_items(_file_declarations, paths)
    for path in paths:
        for event in per_file[path]:
            if event[0] == "depends":
                _kind, model, method, method_depends = event
                depends[model][method].extend(method_depends)
                continue
            _kind, model, name, declared, given, line = event
            known = fields[model].get(name)
            fields[model][name] = (
                declared if known is None else _merged(known, declared, given)
            )
            where.setdefault((model, name), f"{path}:{line}")
    return fields, depends, where


def _merged(known: Declared, declared: Declared, given: frozenset[str]) -> Declared:
    changes = {
        name: getattr(declared, name)
        for name in ("related", "compute", "store", "compute_sudo")
        if name in given
    }
    if given & {"groups", "classification"}:
        changes["access"] = True
    if "discloses" in given:
        changes["discloses"] = True
    return replace(known, **changes)


def _field(
    declarations: tuple, model: str, name: str, seen: frozenset[str] = frozenset()
) -> Declared | None:
    # the field as the model sees it: its own declarations over its parents'
    fields, _depends, _where = declarations
    info = index.models().get(model)
    result = None
    if info is not None and model not in seen:
        for parent in [*info.inherit, *info.inherits]:
            parent_field = _field(declarations, parent, name, seen | {model})
            if parent_field is not None:
                result = parent_field
    own = fields.get(model, {}).get(name)
    if own is not None:
        result = own if result is None else _combine(result, own)
    return result


def _combine(parent: Declared, own: Declared) -> Declared:
    return Declared(
        access=parent.access or own.access,
        discloses=parent.discloses or own.discloses,
        related=own.related or parent.related,
        compute=own.compute or parent.compute,
        store=own.store if own.store is not None else parent.store,
        compute_sudo=own.compute_sudo
        if own.compute_sudo is not None
        else parent.compute_sudo,
    )


def _sensitive(declarations: tuple, model: str, name: str, depth: int = 0) -> bool:
    declared = _field(declarations, model, name)
    if declared is None:
        return False
    if declared.access:
        return True
    if declared.related and depth < 8:
        return _path_hides(
            declarations, model, declared.related, depth + 1, include_last=True
        )
    return False


def _path_hides(
    declarations: tuple, model: str, path: str, depth: int, *, include_last: bool
) -> bool:
    owner: str | None = model
    parts = path.split(".")
    for position, part in enumerate(parts):
        if owner is None:
            return False
        last = position == len(parts) - 1
        if (include_last or not last) and _sensitive(declarations, owner, part, depth):
            return True
        field_info = index.fields_of(owner).get(part)
        if field_info is None:
            return False
        owner = index.comodel_of(owner, field_info)
    return False


def derived_findings(paths: tuple[Path, ...] | None = None) -> list[str]:
    declarations = _declarations(tuple(_paths()) if paths is None else paths)
    fields, depends, where = declarations
    findings = []
    for model, declared_fields in fields.items():
        for name in declared_fields:
            declared = _field(declarations, model, name)
            if declared is None or declared.access or declared.discloses:
                continue
            if declared.related:
                # a related field takes its target's access: only the hops on
                # the way can hide something the target does not
                paths, include_last = [declared.related], False
            elif declared.compute and (declared.store or declared.compute_sudo):
                paths, include_last = depends[model].get(declared.compute, []), True
            else:
                continue
            if any(
                _path_hides(declarations, model, path, 0, include_last=include_last)
                for path in paths
            ):
                findings.append(f"{where[model, name]} {model}.{name}")
    return findings
