import ast
from collections.abc import Mapping
from typing import TYPE_CHECKING

from odoo.tools import SQL

if TYPE_CHECKING:
    from odoo.db import BaseCursor

CODE_COLUMNS = {
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

CODE_CONTEXT_MODELS = {
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

METHOD_RENAMES = {
    "_missing_template_error": "_prepare_missing_template_error",
    "_check_uid_passwd": "_authenticate_rpc_credentials",
    "_check_uid_passwd_cached": "_authenticate_rpc_credentials_cached",
    "_check_review": "_get_impact_reviewed",
    "_check_session_binding": "_is_session_binding_valid",
    "_check_company_domain": "_get_domain_company_compatible",
    "_known_readable": "_has_cached_read_access",
    "_assert_can_auth": "_admit_authentication_attempt",
    "_assert_group_query_allowed": "_check_group_query_allowed",
    "_deny_missing_actions": "_update_action_attributes_for_access",
    "_ensure_private_facet": "_get_or_create_private_facet",
    "_find_free_window": "_get_window_free",
    "_refuse_recombination": "_handle_recombination_error",
    "_refuse_start": "_revoke_for_start_error",
    "_seed_configurations": "_sync_configurations",
    "_validates_whole": "_is_whole_view_validation_requested",
}

MODEL_METHOD_RENAMES = {
    ("res.users", "_check_credentials"): "_authenticate_credentials",
    ("res.users.apikeys", "_check_credentials"): "_get_user_id_for_key",
    ("ir.asset.build", "_sweep"): "_remove_expired_builds_and_get_count",
    ("ir.asset.build", "_sweep_orphan_rows"): "_remove_orphan_rows_and_get_count",
    ("ir.attachment", "_sweep_stored_file"): "_remove_stored_file_if_marker_unchanged",
    ("ir.ui.view", "_validate"): "_request_view_validation",
    ("access.link", "_find_reusable"): "_get_link_and_token_reusable",
    ("ir.asset.build", "_find_reusable"): "_get_build_reusable",
    ("ir.access.drift", "_find"): "_get_findings_by_identity",
    ("ir.access.exception", "_find"): "_get_exception_active",
}

SHARED_MODEL_METHOD_RENAMES = {
    **METHOD_RENAMES,
    "_check_access": "_get_records_forbidden_and_error_factory",
}

GENERIC_METHOD_NAMES = (
    frozenset(old for _, old in MODEL_METHOD_RENAMES)
    | SHARED_MODEL_METHOD_RENAMES.keys()
)

ERROR_METHOD_MODELS = {
    "_deny_login": "res.users",
    "_raise_currently_executing": "ir.cron",
}

RECORDSET_METHODS = frozenset(
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


class _GenericMethodBindings(ast.NodeVisitor):
    def __init__(
        self,
        code: str,
        model: str | None,
        relations: Mapping[tuple[str, str], str],
        context_models: Mapping[str, str] | None = None,
    ) -> None:
        self.code = code.encode()
        self.context_models = (
            dict.fromkeys(("model", "record", "records", "self"), model)
            if model is not None
            else {}
        )
        self.context_models.update(context_models or {})
        self.relations = relations
        self.bindings: dict[int, dict[str, list[ast.expr]]] = {}
        self.scopes: dict[int, int] = {}
        self.scope_parents: dict[int, int] = {}
        self.ancestors: dict[int, tuple[ast.AST, ...]] = {}
        self.binding_guards: dict[int, tuple[ast.AST, ...]] = {}
        self.locals: dict[int, set[str]] = {}
        self.uncertain: dict[int, set[str]] = {}
        self.edits: dict[int, tuple[int, bytes]] = {}
        self.unresolved: set[tuple[str, int]] = set()
        self.line_starts = [0]
        for line in self.code.splitlines(keepends=True):
            self.line_starts.append(self.line_starts[-1] + len(line))

    def _record_shadowed_names(self, node: ast.AST, scope: int) -> None:
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            self.locals.setdefault(scope, set()).add(node.id)
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            self.uncertain.setdefault(scope, set()).update(node.names)
            self.locals.setdefault(scope, set()).update(node.names)
        if isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
            self.locals.setdefault(scope, set()).add(node.name)

    def add_bindings(self, tree: ast.AST) -> None:
        def collect(
            node: ast.AST, scope: int, ancestors: tuple[ast.AST, ...] = ()
        ) -> None:
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
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ):
                    self.locals.setdefault(scope, set()).add(node.name)
                self.scope_parents[id(node)] = scope
                scope = id(node)
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
                ):
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
            self.scopes[id(node)] = scope
            self.ancestors[id(node)] = ancestors
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                self.locals.setdefault(scope, set()).update(
                    alias.asname or alias.name.split(".")[0] for alias in node.names
                )
            if isinstance(node, ast.ExceptHandler) and node.name:
                self.locals.setdefault(scope, set()).add(node.name)
            self._record_shadowed_names(node, scope)
            targets = []
            if isinstance(node, ast.Assign):
                targets = node.targets
                value = node.value
            elif isinstance(node, ast.NamedExpr):
                targets = [node.target]
                value = node.value
            elif isinstance(node, (ast.For, ast.AsyncFor)):
                targets = [node.target]
                value = node.iter
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
                    ),
                )
            )
            if isinstance(node, (ast.For, ast.AsyncFor)):
                guards += (node,)
            if isinstance(node, (ast.AugAssign, ast.Delete)):
                for child in ast.walk(node):
                    if isinstance(child, ast.Name) and isinstance(
                        child.ctx, (ast.Store, ast.Del)
                    ):
                        self.uncertain.setdefault(scope, set()).add(child.id)
            for target in targets:
                if isinstance(target, ast.Name):
                    if guards and not isinstance(node, (ast.For, ast.AsyncFor)):
                        self.uncertain.setdefault(scope, set()).add(target.id)
                    self.binding_guards[id(value)] = guards
                    self.bindings.setdefault(scope, {}).setdefault(
                        target.id, []
                    ).append(value)
            for child in ast.iter_child_nodes(node):
                collect(child, scope, ancestors + (node,))

        collect(tree, id(tree))

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
        self, node: ast.AST, seen: frozenset[str] = frozenset()
    ) -> str | None:
        if isinstance(node, ast.Name):
            if node.id in seen:
                return None
            scope = self.scopes[id(node)]
            if node.id in self.uncertain.get(scope, set()):
                return None
            candidates = [
                value
                for value in self.bindings.get(scope, {}).get(node.id, [])
                if (value.lineno, value.col_offset) < (node.lineno, node.col_offset)
                and all(
                    guard in self.ancestors[id(node)]
                    for guard in self.binding_guards[id(value)]
                )
            ]
            if candidates:
                models = {
                    self._resolve_model(value, seen | {node.id}) for value in candidates
                }
                return next(iter(models)) if len(models) == 1 else None
            return (
                self.context_models.get(node.id)
                if self._is_context_name_unshadowed(node)
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
            if node.func.attr in RECORDSET_METHODS:
                return self._resolve_model(node.func.value, seen)
        return None

    def _resolve_method_name(self, old: str, owner: ast.AST) -> str | None:
        model = self._resolve_model(owner)
        if model is not None:
            return MODEL_METHOD_RENAMES.get(
                (model, old)
            ) or SHARED_MODEL_METHOD_RENAMES.get(old)
        return None

    def _rename_attribute(self, node: ast.Attribute, new: str) -> None:
        assert node.end_lineno is not None and node.end_col_offset is not None
        end = self.line_starts[node.end_lineno - 1] + node.end_col_offset
        start = end - len(node.attr)
        assert self.code[start:end] == node.attr.encode()
        self.edits[start] = (end, new.encode())

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in GENERIC_METHOD_NAMES:
            if new := self._resolve_method_name(node.attr, node.value):
                self._rename_attribute(node, new)
            elif self._resolve_model(node.value) is None:
                self.unresolved.add((node.attr, node.lineno))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in GENERIC_METHOD_NAMES
        ):
            if new := self._resolve_method_name(node.func.attr, node.func.value):
                self._rename_attribute(node.func, new)
        elif (
            isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and self._is_context_name_unshadowed(node.func)
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value in GENERIC_METHOD_NAMES
        ):
            value = node.args[1]
            if new := self._resolve_method_name(value.value, node.args[0]):
                assert value.end_lineno is not None and value.end_col_offset is not None
                start = self.line_starts[value.lineno - 1] + value.col_offset
                end = self.line_starts[value.end_lineno - 1] + value.end_col_offset
                self.edits[start] = (end, repr(new).encode())
            elif self._resolve_model(node.args[0]) is None:
                self.unresolved.add((value.value, node.lineno))
        self.generic_visit(node)

    def rewrite(self) -> str:
        code = self.code
        for start, (end, replacement) in sorted(self.edits.items(), reverse=True):
            code = code[:start] + replacement + code[end:]
        return code.decode()


def _rewrite_generic_method_bindings(
    code: str,
    model: str | None,
    relations: Mapping[tuple[str, str], str],
    unresolved: set[tuple[str, int]] | None = None,
    *,
    context_models: Mapping[str, str] | None = None,
) -> str:
    tree = ast.parse(code)
    rewriter = _GenericMethodBindings(code, model, relations, context_models)
    rewriter.add_bindings(tree)
    rewriter.visit(tree)
    if unresolved is not None:
        unresolved.update(rewriter.unresolved)
    return rewriter.rewrite()


def _rewrite_error_method_calls(
    code: str,
    model: str | None,
    relations: Mapping[tuple[str, str], str],
    *,
    context_models: Mapping[str, str] | None = None,
) -> str:
    tree = ast.parse(code)
    parents = {
        child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)
    }
    rewriter = _GenericMethodBindings(code, model, relations, context_models)
    rewriter.add_bindings(tree)
    _check_error_method_reflections(tree, rewriter)
    names = {
        node.id if isinstance(node, ast.Name) else node.arg
        for node in ast.walk(tree)
        if isinstance(node, (ast.Name, ast.arg))
    }
    names.update(
        name for local_names in rewriter.locals.values() for name in local_names
    )
    temporary = "login_error_owner"
    while temporary in names:
        temporary += "_"
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or node.attr not in ERROR_METHOD_MODELS:
            continue
        owner = rewriter._resolve_model(node.value)
        if owner is not None and owner != ERROR_METHOD_MODELS[node.attr]:
            continue
        call = parents.get(node)
        statement = parents.get(call)
        if owner is None or not (
            isinstance(call, ast.Call)
            and call.func is node
            and isinstance(statement, (ast.Expr, ast.Return))
            and statement.value is call
        ):
            raise ValueError(
                f"Cannot migrate {node.attr} at line {node.lineno}: resolve its model and use a standalone call first"
            )
        receiver = ast.unparse(node.value)
        if node.attr == "_raise_currently_executing":
            factory = ast.Call(
                func=ast.Attribute(
                    value=node.value, attr="_prepare_cron_running_error", ctx=ast.Load()
                ),
                args=call.args,
                keywords=call.keywords,
            )
            replacement = f"raise {ast.unparse(factory)} from None"
        else:
            spend = ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id=temporary, ctx=ast.Load()),
                    attr="_spend_password_cost",
                    ctx=ast.Load(),
                ),
                args=call.args,
                keywords=call.keywords,
            )
            replacement = f"{temporary} = {receiver}; {ast.unparse(spend)}; raise {temporary}._prepare_login_denied_error()"
        start = rewriter.line_starts[statement.lineno - 1] + statement.col_offset
        end = rewriter.line_starts[statement.end_lineno - 1] + statement.end_col_offset
        rewriter.edits[start] = (end, replacement.encode())
    return rewriter.rewrite()


def _check_error_method_reflections(
    tree: ast.AST, rewriter: _GenericMethodBindings
) -> None:
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and rewriter._is_context_name_unshadowed(node.func)
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value in ERROR_METHOD_MODELS
        ):
            continue
        old = node.args[1].value
        owner = rewriter._resolve_model(node.args[0])
        if owner is None or owner == ERROR_METHOD_MODELS[old]:
            raise ValueError(
                f"Cannot migrate {old} at line {node.lineno}: use a direct standalone call first"
            )


def _rename_generic_model_methods(
    cr: BaseCursor, columns: set[tuple[str, str]]
) -> None:
    cr.execute("SELECT id, model FROM ir_model")
    models = dict(cr.fetchall())
    cr.execute(
        "SELECT m.model, f.name, f.relation FROM ir_model_fields f "
        "JOIN ir_model m ON m.id = f.model_id WHERE f.relation IS NOT NULL"
    )
    relations = {(model, name): relation for model, name, relation in cr.fetchall()}
    for table, names in CODE_COLUMNS.items():
        for name in names:
            if (table, name) not in columns:
                continue
            owner = (
                SQL.identifier("model_id")
                if (table, "model_id") in columns
                else (
                    SQL("(SELECT model_id FROM ir_act_server WHERE id = action_id)")
                    if table == "ir_actions_server_history"
                    else SQL("NULL")
                )
            )
            cr.execute(
                SQL(
                    "SELECT id, %s, %s FROM %s WHERE %s ~ %s",
                    SQL.identifier(name),
                    owner,
                    SQL.identifier(table),
                    SQL.identifier(name),
                    rf"\y({'|'.join(sorted(GENERIC_METHOD_NAMES | ERROR_METHOD_MODELS.keys()))})\y",
                )
            )
            for row_id, code, model_id in cr.fetchall():
                unresolved = set()
                try:
                    rewritten = _rewrite_generic_method_bindings(
                        code,
                        models.get(model_id),
                        relations,
                        unresolved,
                        context_models=CODE_CONTEXT_MODELS.get(table),
                    )
                    if unresolved:
                        raise ValueError(
                            f"Cannot resolve method owners: {sorted(unresolved)}; "
                            "resolve these bindings before upgrading"
                        )
                    rewritten = _rewrite_error_method_calls(
                        rewritten,
                        models.get(model_id),
                        relations,
                        context_models=CODE_CONTEXT_MODELS.get(table),
                    )
                except (SyntaxError, ValueError) as error:
                    raise ValueError(
                        f"{table}.{name}, row {row_id}: {error}"
                    ) from error
                if rewritten != code:
                    cr.execute(
                        SQL(
                            "UPDATE %s SET %s = %s WHERE id = %s",
                            SQL.identifier(table),
                            SQL.identifier(name),
                            rewritten,
                            row_id,
                        )
                    )


def migrate(cr: BaseCursor, version: str | None) -> None:
    if not version:
        return
    cr.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = ANY(%s)",
        [list(CODE_COLUMNS)],
    )
    columns = set(cr.fetchall())
    _rename_generic_model_methods(cr, columns)
