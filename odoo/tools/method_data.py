from __future__ import annotations

import ast
import dataclasses
import re
import unicodedata
from collections.abc import Mapping
from typing import TYPE_CHECKING, NamedTuple, override

from odoo.libs.sql import SQL

if TYPE_CHECKING:
    from odoo.db import BaseCursor


_CODE_COLUMNS = {
    "ir_act_server": ("code",),
    "ir_actions_server_history": ("code",),
    "ir_model_fields": ("compute",),
    "hr_salary_rule": (
        "amount_python_compute",
        "condition_python",
        "amount_percentage_base",
        "quantity",
    ),
    "hr_payroll_dashboard_warning": ("evaluation_code",),
}

_CODE_CONTEXT_MODELS = {
    "hr_salary_rule": {
        "payslip": "hr.payslip",
        "employee": "hr.employee",
        "version": "hr.version",
    },
    "hr_payroll_dashboard_warning": {
        "self": "hr.payslip",
        "last_batches": "hr.payslip.run",
        "warning_records": "base",
    },
}

_RECORDSET_METHODS = frozenset(
    {
        "sudo",
        "with_privilege",
        "with_context",
        "with_env",
        "with_user",
        "with_company",
        "browse",
        "search",
        "search_fetch",
        "exists",
        "filtered",
        "sorted",
        "new",
        "create",
    }
)


class _BindingAssignment(NamedTuple):
    targets: list[ast.expr]
    value: ast.expr


class _ModelMethodReferences(ast.NodeVisitor):
    def __init__(
        self,
        code: str,
        model: str | None,
        relations: Mapping[tuple[str, str], str],
        context_models: Mapping[str, str] | None = None,
        model_parents: Mapping[str, set[str]] | None = None,
        *,
        model_method_renames: Mapping[tuple[str, str], str],
        shared_method_renames: Mapping[str, str],
    ) -> None:
        self.model_method_renames = model_method_renames
        self.shared_method_renames = shared_method_renames
        self.method_names = (
            frozenset(old for _, old in model_method_renames)
            | shared_method_renames.keys()
        )
        self.code = code.encode()
        self.context_models = (
            dict.fromkeys(("model", "record", "records", "self"), model)
            if model is not None
            else {}
        )
        self.context_models.update(context_models or {})
        self.relations = relations
        self.model_parents = model_parents or {}
        self.bindings: dict[int, dict[str, list[ast.expr]]] = {}
        self.scopes: dict[int, int] = {}
        self.scope_parents: dict[int, int] = {}
        self.comprehension_scopes: set[int] = set()
        self.ancestors: dict[int, tuple[ast.AST, ...]] = {}
        self.binding_guards: dict[int, tuple[ast.AST, ...]] = {}
        self.locals: dict[int, set[str]] = {}
        self.uncertain: dict[int, set[str]] = {}
        self.edits: dict[int, tuple[int, bytes]] = {}
        self.unresolved: set[tuple[str, int]] = set()
        self.method_name_literals: set[str] = set()
        self.line_starts = [0]
        for line in self.code.splitlines(keepends=True):
            self.line_starts.append(self.line_starts[-1] + len(line))

    def _mark_bindings_uncertain(self, scope: int, *names: str) -> None:
        self.locals.setdefault(scope, set()).update(names)
        self.uncertain.setdefault(scope, set()).update(names)

    def _record_shadowed_names(self, node: ast.AST, scope: int) -> None:
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            self.locals.setdefault(scope, set()).add(node.id)
            parent = self.ancestors[id(node)][-1]
            if not isinstance(
                parent,
                (ast.Assign, ast.AnnAssign, ast.NamedExpr, ast.For, ast.AsyncFor),
            ):
                self._mark_bindings_uncertain(scope, node.id)
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            self._mark_bindings_uncertain(
                scope,
                *(alias.asname or alias.name.split(".")[0] for alias in node.names),
            )
        if isinstance(node, ast.ExceptHandler) and node.name:
            self._mark_bindings_uncertain(scope, node.name)
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            self._mark_bindings_uncertain(scope, *node.names)
            if isinstance(node, ast.Global):
                self._mark_bindings_uncertain(self.module_scope, *node.names)
            else:
                while scope in self.scope_parents:
                    scope = self.scope_parents[scope]
                    self._mark_bindings_uncertain(scope, *node.names)
        if isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
            self._mark_bindings_uncertain(scope, node.name)
        if isinstance(node, ast.MatchMapping) and node.rest:
            self._mark_bindings_uncertain(scope, node.rest)
        if isinstance(node, ast.NamedExpr) and scope in self.comprehension_scopes:
            self._mark_bindings_uncertain(scope, node.target.id)
            while scope in self.comprehension_scopes:
                scope = self.scope_parents[scope]
            self._mark_bindings_uncertain(scope, node.target.id)

    def add_bindings(self, tree: ast.AST) -> None:
        self.module_scope = id(tree)
        self.method_name_literals = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value in self.method_names
        }

        self._add_node_bindings(tree, id(tree))

    def _add_node_scope(self, node: ast.AST, scope: int) -> int:
        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.Lambda,
                ast.ClassDef,
                ast.ListComp,
                ast.SetComp,
                ast.DictComp,
                ast.GeneratorExp,
            ),
        ):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self._mark_bindings_uncertain(scope, node.name)
            self.scope_parents[id(node)] = scope
            scope = id(node)
            if isinstance(
                node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
            ):
                self.comprehension_scopes.add(scope)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                arguments = node.args
                self.locals.setdefault(scope, set()).update(
                    arg.arg
                    for arg in (
                        *arguments.posonlyargs,
                        *arguments.args,
                        *arguments.kwonlyargs,
                    )
                )
                for arg in (arguments.vararg, arguments.kwarg):
                    if arg is not None:
                        self.locals[scope].add(arg.arg)
        return scope

    def _resolve_binding_assignment(self, node: ast.AST) -> _BindingAssignment | None:
        if isinstance(node, ast.Assign):
            return _BindingAssignment(node.targets, node.value)
        if isinstance(node, (ast.AnnAssign, ast.NamedExpr)) and node.value is not None:
            return _BindingAssignment([node.target], node.value)
        if isinstance(node, (ast.For, ast.AsyncFor)):
            return _BindingAssignment([node.target], node.iter)
        return None

    def _get_binding_guards(
        self, node: ast.AST, ancestors: tuple[ast.AST, ...]
    ) -> tuple[ast.AST, ...]:
        guards = tuple(
            parent
            for parent in ancestors
            if isinstance(
                parent,
                (
                    ast.If,
                    ast.For,
                    ast.AsyncFor,
                    ast.While,
                    ast.Try,
                    ast.TryStar,
                    ast.Match,
                    ast.BoolOp,
                    ast.IfExp,
                    ast.Compare,
                ),
            )
        )
        if isinstance(node, (ast.For, ast.AsyncFor)):
            guards += (node,)
        return guards

    def _add_assignment_bindings(
        self, node: ast.AST, scope: int, ancestors: tuple[ast.AST, ...]
    ) -> None:
        assignment = self._resolve_binding_assignment(node)
        if assignment is None:
            return
        guards = self._get_binding_guards(node, ancestors)
        value = assignment.value
        for target in assignment.targets:
            if isinstance(target, ast.Name):
                if guards and not isinstance(node, (ast.For, ast.AsyncFor)):
                    self.uncertain.setdefault(scope, set()).add(target.id)
                self.binding_guards[id(value)] = guards
                self.bindings.setdefault(scope, {}).setdefault(target.id, []).append(
                    value
                )

    def _add_node_bindings(
        self, node: ast.AST, scope: int, ancestors: tuple[ast.AST, ...] = ()
    ) -> None:
        scope = self._add_node_scope(node, scope)
        self.scopes[id(node)] = scope
        self.ancestors[id(node)] = ancestors
        self._record_shadowed_names(node, scope)
        self._add_assignment_bindings(node, scope, ancestors)
        for child in ast.iter_child_nodes(node):
            self._add_node_bindings(child, scope, ancestors + (node,))

    def _is_context_name_unshadowed(self, node: ast.Name) -> bool:
        scope = self.scopes[id(node)]
        while True:
            if node.id in self.locals.get(scope, set()):
                return False
            if scope not in self.scope_parents:
                return True
            scope = self.scope_parents[scope]

    def _is_environment(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Name) and node.id == "env":
            return self._is_context_name_unshadowed(node)
        if isinstance(node, ast.Attribute) and node.attr == "env":
            return self._resolve_model(node.value) is not None
        return (
            isinstance(node, ast.Attribute)
            and node.attr == "registry"
            and self._is_environment(node.value)
        )

    def _resolve_model(
        self, node: ast.AST, seen: frozenset[int] = frozenset()
    ) -> str | None:
        if isinstance(node, ast.Name):
            if id(node) in seen:
                return None
            scope = self.scopes[id(node)]
            if node.id in self.uncertain.get(scope, set()):
                return None
            candidates = [
                value
                if all(
                    guard in self.ancestors[id(node)]
                    for guard in self.binding_guards[id(value)]
                )
                else None
                for value in self.bindings.get(scope, {}).get(node.id, [])
                if (value.lineno, value.col_offset) < (node.lineno, node.col_offset)
            ]
            if candidates:
                value = candidates[-1]
                return (
                    self._resolve_model(value, seen | {id(node)})
                    if value is not None
                    else None
                )
            return (
                self.context_models.get(node.id)
                if scope == self.module_scope or self._is_context_name_unshadowed(node)
                else None
            )
        if isinstance(node, ast.NamedExpr):
            return self._resolve_model(node.value, seen)
        if isinstance(node, ast.Subscript):
            if isinstance(node.slice, ast.Constant) and isinstance(
                node.slice.value, str
            ):
                if self._is_environment(node.value):
                    return node.slice.value
                owner = self._resolve_model(node.value, seen)
                return self.relations.get((owner, node.slice.value)) if owner else None
            if isinstance(node.slice, ast.Slice) or (
                isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, int)
            ):
                return self._resolve_model(node.value, seen)
            return None
        if isinstance(node, ast.Attribute):
            owner = self._resolve_model(node.value, seen)
            return self.relations.get((owner, node.attr)) if owner else None
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in _RECORDSET_METHODS:
                return self._resolve_model(node.func.value, seen)
        return None

    def _resolve_method_name(self, old: str, owner: ast.AST) -> str | None:
        model = self._resolve_model(owner)
        if model is None:
            return None
        if new := self.model_method_renames.get((model, old)):
            return new
        inherited = {
            new
            for parent in self._get_model_ancestors(model)
            if (new := self.model_method_renames.get((parent, old)))
        }
        if len(inherited) > 1:
            raise ValueError(
                f"Cannot migrate {old} on {model}: conflicting inherited methods {sorted(inherited)}"
            )
        return next(iter(inherited), self.shared_method_renames.get(old))

    def _get_model_ancestors(self, model: str) -> set[str]:
        ancestors = set()
        pending = [model]
        while pending:
            for parent in self.model_parents.get(pending.pop(), ()):
                if parent not in ancestors and parent != model:
                    ancestors.add(parent)
                    pending.append(parent)
        return ancestors

    def _get_possible_strings(
        self, node: ast.AST, seen: frozenset[int] = frozenset()
    ) -> set[str | None]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return {node.value}
        if not isinstance(node, ast.Name) or id(node) in seen:
            return {None, *self.method_name_literals}
        scope = self.scopes[id(node)]
        results: set[str | None] = set()
        if node.id in self.uncertain.get(scope, set()):
            results.add(None)
        candidates = [
            value
            for value in self.bindings.get(scope, {}).get(node.id, [])
            if (value.lineno, value.col_offset) < (node.lineno, node.col_offset)
        ]
        if candidates:
            value = candidates[-1]
            if isinstance(self.ancestors[id(value)][-1], (ast.For, ast.AsyncFor)):
                results.add(None)
            else:
                results.update(self._get_possible_strings(value, seen | {id(node)}))
            if self.binding_guards[id(value)]:
                results.add(None)
        if not results or None in results:
            results.update((None, *self.method_name_literals))
        return results

    def _rename_attribute(self, node: ast.Attribute, new: str) -> None:
        assert node.end_lineno is not None and node.end_col_offset is not None
        end = self.line_starts[node.end_lineno - 1] + node.end_col_offset
        start = end - len(node.attr.encode())
        if self.code[start:end] != node.attr.encode():
            prefix = self.code[self.line_starts[node.end_lineno - 1] : end].decode()
            position = len(prefix)
            while position and ("a" + prefix[position - 1]).isidentifier():
                position -= 1
            assert unicodedata.normalize("NFKC", prefix[position:]) == node.attr
            start = self.line_starts[node.end_lineno - 1] + len(
                prefix[:position].encode()
            )
        self.edits[start] = (end, new.encode())

    @override
    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in self.method_names:
            if new := self._resolve_method_name(node.attr, node.value):
                self._rename_attribute(node, new)
            elif self._resolve_model(node.value) is None:
                self.unresolved.add((node.attr, node.lineno))
        self.generic_visit(node)

    @override
    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and node.func.attr in self.method_names:
            if new := self._resolve_method_name(node.func.attr, node.func.value):
                self._rename_attribute(node.func, new)
        elif (
            isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and self._is_context_name_unshadowed(node.func)
            and len(node.args) >= 2
        ):
            value = node.args[1]
            strings = self._get_possible_strings(value)
            names = {
                value
                for value in strings
                if value is not None and value in self.method_names
            }
            if (
                len(strings) == 1
                and names
                and (new := self._resolve_method_name(next(iter(names)), node.args[0]))
            ):
                assert value.end_lineno is not None and value.end_col_offset is not None
                start = self.line_starts[value.lineno - 1] + value.col_offset
                end = self.line_starts[value.end_lineno - 1] + value.end_col_offset
                self.edits[start] = (end, repr(new).encode())
            elif (
                None in strings
                or len(strings) != 1
                or self._resolve_model(node.args[0]) is None
            ):
                if (
                    not names
                    and None in strings
                    and self._resolve_model(node.args[0]) is not None
                ):
                    names.update(
                        old
                        for old in self.method_names
                        if self._resolve_method_name(old, node.args[0]) is not None
                    )
                self.unresolved.update(
                    (old, node.lineno)
                    for old in names
                    if self._resolve_model(node.args[0]) is None
                    or self._resolve_method_name(old, node.args[0]) is not None
                )
        self.generic_visit(node)

    def rewrite(self) -> str:
        code = self.code
        for start, (end, replacement) in sorted(self.edits.items(), reverse=True):
            code = code[:start] + replacement + code[end:]
        return code.decode()


@dataclasses.dataclass(frozen=True, slots=True)
class MethodReferenceRewrite:
    code: str
    unresolved: frozenset[tuple[str, int]]


def rewrite_model_method_references(
    code: str,
    model: str | None,
    relations: Mapping[tuple[str, str], str],
    *,
    model_method_renames: Mapping[tuple[str, str], str],
    shared_method_renames: Mapping[str, str] | None = None,
    context_models: Mapping[str, str] | None = None,
    model_parents: Mapping[str, set[str]] | None = None,
) -> MethodReferenceRewrite:
    tree = ast.parse(code)
    rewriter = _ModelMethodReferences(
        code,
        model,
        relations,
        context_models,
        model_parents,
        model_method_renames=model_method_renames,
        shared_method_renames=shared_method_renames or {},
    )
    rewriter.add_bindings(tree)
    rewriter.visit(tree)
    return MethodReferenceRewrite(rewriter.rewrite(), frozenset(rewriter.unresolved))


@dataclasses.dataclass(frozen=True, slots=True)
class _ModelReferenceCatalog:
    models: Mapping[int, str]
    relations: Mapping[tuple[str, str], str]
    parents: Mapping[str, set[str]]


def _get_model_reference_catalog(
    cr: BaseCursor, columns: set[tuple[str, str]]
) -> _ModelReferenceCatalog:
    cr.execute("SELECT id, model FROM ir_model")
    models = dict(cr.fetchall())
    cr.execute(
        "SELECT m.model, f.name, f.relation FROM ir_model_fields f "
        "JOIN ir_model m ON m.id = f.model_id WHERE f.relation IS NOT NULL"
    )
    relations = {(model, name): relation for model, name, relation in cr.fetchall()}
    model_parents: dict[str, set[str]] = {}
    if all(
        ("ir_model_inherit", column) in columns
        for column in ("model_id", "parent_id", "parent_field_id")
    ):
        cr.execute(
            "SELECT model_id, parent_id FROM ir_model_inherit WHERE parent_field_id IS NULL"
        )
        for model_id, parent_id in cr.fetchall():
            model_parents.setdefault(models[model_id], set()).add(models[parent_id])
    return _ModelReferenceCatalog(models, relations, model_parents)


def _prepare_stored_code_owner_sql(table: str, columns: set[tuple[str, str]]) -> SQL:
    if (table, "model_id") in columns:
        return SQL.identifier("model_id")
    if table == "ir_actions_server_history":
        return SQL("(SELECT model_id FROM ir_act_server WHERE id = action_id)")
    return SQL("NULL")


def _rename_stored_code_column(
    cr: BaseCursor,
    table: str,
    name: str,
    owner: SQL,
    pattern: str,
    catalog: _ModelReferenceCatalog,
    model_method_renames: Mapping[tuple[str, str], str],
    shared_method_renames: Mapping[str, str],
) -> None:
    cr.execute(
        SQL(
            "SELECT id, %s, %s FROM %s WHERE normalize(%s, NFKC) ~ %s OR %s ~ %s",
            SQL.identifier(name),
            owner,
            SQL.identifier(table),
            SQL.identifier(name),
            pattern,
            SQL.identifier(name),
            r"\ygetattr\y",
        )
    )
    for row_id, code, model_id in cr.fetchall():
        try:
            result = rewrite_model_method_references(
                code,
                catalog.models.get(model_id),
                catalog.relations,
                model_method_renames=model_method_renames,
                shared_method_renames=shared_method_renames,
                context_models=_CODE_CONTEXT_MODELS.get(table),
                model_parents=catalog.parents,
            )
            if result.unresolved:
                raise ValueError(
                    f"Cannot resolve method owners: {sorted(result.unresolved)}; "
                    "resolve these bindings before upgrading"
                )
        except (SyntaxError, ValueError) as error:
            raise ValueError(f"{table}.{name}, row {row_id}: {error}") from error
        if result.code != code:
            cr.execute(
                SQL(
                    "UPDATE %s SET %s = %s WHERE id = %s",
                    SQL.identifier(table),
                    SQL.identifier(name),
                    result.code,
                    row_id,
                )
            )


def rename_stored_model_methods(
    cr: BaseCursor,
    *,
    model_method_renames: Mapping[tuple[str, str], str],
    shared_method_renames: Mapping[str, str] | None = None,
) -> None:
    shared = shared_method_renames or {}
    names = frozenset(old for _, old in model_method_renames) | shared.keys()
    if not names:
        return
    cr.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = ANY(%s)",
        [[*_CODE_COLUMNS, "ir_model_inherit"]],
    )
    columns = set(cr.fetchall())
    catalog = _get_model_reference_catalog(cr, columns)
    pattern = rf"\y({'|'.join(re.escape(name) for name in sorted(names))})\y"
    for table, column_names in _CODE_COLUMNS.items():
        for name in column_names:
            if (table, name) in columns:
                _rename_stored_code_column(
                    cr,
                    table,
                    name,
                    _prepare_stored_code_owner_sql(table, columns),
                    pattern,
                    catalog,
                    model_method_renames,
                    shared,
                )
