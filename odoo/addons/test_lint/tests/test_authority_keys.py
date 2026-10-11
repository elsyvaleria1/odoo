import ast
import functools
import re
from collections import defaultdict
from pathlib import Path

from . import _production_python, lint_case

_CONTEXT_ATTRIBUTES = frozenset({"context", "_context"})
_CONTEXT_NAMES = frozenset({"context", "ctx"})
_SUBJECT_KEYS = frozenset(
    {
        "active_domain",
        "active_id",
        "active_ids",
        "active_model",
        "lang",
        "module",
        "params",
        "raise_if_not_found",
        "res_id",
        "tz",
        "view",
        "active_mo_id",
        "active_picking_id",
        "active_repair_id",
        "child_field",
        "link_to_project",
        "order_id",
        "product_catalog_order_model",
        "hr_payroll_payment_register",
        "hr_payroll_payment_register_batch",
        "quality_wizard_id",
        "selected_employee_id",
        "split_line_id",
        "st_line_id",
        "website_id",
    }
)
_INPUT_KEYS = frozenset(
    {
        "action_name",
        "authorization_code",
        "client_data",
        "cloned_templates",
        "create_for_employee_mapping",
        "create_user",
        "exception_scope",
        "fill_temporal",
        "force_email",
        "force_periodicity_violation",
        "from_emission_factor_line",
        "import_file",
        "invoice_state",
        "lock_date_field",
        "raise_if_nothing_to_invoice",
        "raise_no_imported_file",
        "requested_change_field",
        "no_mail_to_attendees",
        "round_281_45",
        "selected_analytic_plan",
        "sign_all",
        "validate_analytic",
    }
)
_MODE_KEYS = frozenset({"from_embedded_action", "mrp_display", "salary_simulation"})
_SUBJECT_PATTERN = re.compile(r"^default_|_view_ref$")
_CHECK_CALL = re.compile(r"^(_?check_|_check|_validate)")
_DECLARE = "declare_authority_keys"


def _is_context(node: ast.AST) -> bool:
    return (isinstance(node, ast.Attribute) and node.attr in _CONTEXT_ATTRIBUTES) or (
        isinstance(node, ast.Name) and node.id in _CONTEXT_NAMES
    )


def _literal(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def context_key(node: ast.AST) -> str | None:
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and _is_context(node.func.value)
        and node.args
    ):
        return _literal(node.args[0])
    if isinstance(node, ast.Subscript) and _is_context(node.value):
        return _literal(node.slice)
    if (
        isinstance(node, ast.Compare)
        and len(node.ops) == 1
        and isinstance(node.ops[0], ast.In | ast.NotIn)
        and _is_context(node.comparators[0])
    ):
        return _literal(node.left)
    return None


def _keys_read(test: ast.AST) -> set[str]:
    return {key for node in ast.walk(test) if (key := context_key(node))}


def _compared_by_identity(test: ast.AST) -> bool:
    return any(
        isinstance(node, ast.Compare)
        and any(isinstance(op, ast.Is | ast.IsNot) for op in node.ops)
        for node in ast.walk(test)
    )


def _statements(body: list[ast.stmt]):
    for statement in body:
        yield statement
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        for name in ("body", "orelse", "finalbody"):
            yield from _statements(getattr(statement, name, None) or [])
        for handler in getattr(statement, "handlers", None) or []:
            yield from _statements(handler.body)
        for case in getattr(statement, "cases", None) or []:
            yield from _statements(case.body)


def _raises(body: list[ast.stmt]) -> bool:
    return any(isinstance(statement, ast.Raise) for statement in _statements(body))


def _calls_a_check(body: list[ast.stmt]) -> bool:
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and _CHECK_CALL.match(node.func.attr)
        for statement in _statements(body)
        for node in ast.walk(statement)
    )


def _only_leaves(body: list[ast.stmt]) -> bool:
    return bool(body) and all(
        isinstance(statement, ast.Return | ast.Continue | ast.Pass)
        or (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
        )
        for statement in body
    )


def is_subject_key(key: str) -> bool:
    return (
        key in _SUBJECT_KEYS
        or key in _INPUT_KEYS
        or key in _MODE_KEYS
        or bool(_SUBJECT_PATTERN.search(key))
    )


def _bound_keys(body: list[ast.stmt]) -> dict[str, str]:
    return {
        statement.targets[0].id: key
        for statement in _statements(body)
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
        and (key := context_key(statement.value))
    }


def gating_reads(tree: ast.AST):
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        bound = _bound_keys(function.body)
        for statement in _statements(function.body):
            if not isinstance(statement, ast.If):
                continue
            keys = _keys_read(statement.test) | {
                bound[node.id]
                for node in ast.walk(statement.test)
                if isinstance(node, ast.Name) and node.id in bound
            }
            if not keys or _compared_by_identity(statement.test):
                continue
            branches = (statement.body, statement.orelse)
            if any(
                _raises(branch) or _calls_a_check(branch) for branch in branches
            ) or (_only_leaves(statement.body) and _raises(function.body)):
                for key in sorted(keys):
                    yield key, statement.lineno


def declared_keys(trees) -> frozenset[str]:
    return frozenset(key for tree in trees for key in _declared_in(tree))


def _declared_in(tree: ast.AST) -> list[str]:
    return [
        key
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (getattr(node.func, "id", None) or getattr(node.func, "attr", None))
        == _DECLARE
        for argument in node.args[1:]
        if (key := _literal(argument)) is not None
    ]


def _authority_facts(tree: ast.Module) -> tuple[list[str], list[tuple[str, int]]]:
    return _declared_in(tree), list(gating_reads(tree))


@functools.cache
def _facts(
    paths: tuple[Path, ...],
) -> dict[Path, tuple[list[str], list[tuple[str, int]]] | None]:
    return _production_python.extract(_authority_facts, paths)


def authority_key_findings(sources, declared) -> dict[str, list[str]]:
    sites: defaultdict[str, defaultdict[str, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
    facts = _facts(tuple(path for *_, path in sources))
    for repo, _module, path in sources:
        _declared, reads = facts[path] or ((), ())
        for key, line in reads:
            if key not in declared and not is_subject_key(key):
                sites[repo][key].append(f"{path}:{line}")
    return {
        repo: [
            f"{key} ({', '.join(where[:3])}{', ...' if len(where) > 3 else ''})"
            for key, where in sorted(keys.items())
        ]
        for repo, keys in sites.items()
    }


def _framework_declarations() -> frozenset[str]:
    paths = [
        Path(path)
        for path in lint_case.framework_paths()
        if _DECLARE in Path(path).read_text(encoding="utf-8", errors="replace")
    ]
    return frozenset(
        key for found in _facts(tuple(paths)).values() if found for key in found[0]
    )


class TestAuthorityKeys(lint_case.LintCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sources = _production_python.production_sources()

    def test_a_key_that_gates_a_check_is_declared(self):
        declared = _framework_declarations() | {
            key
            for found in _facts(tuple(path for *_, path in self.sources)).values()
            if found
            for key in found[0]
        }
        self.assertIn("skip_readonly_check", declared, "the declarations went unread")
        self.assert_ratchet_per_repository(
            authority_key_findings(self.sources, declared),
            "authority_context_key",
            "undeclared context key(s) deciding a check in <repo>",
            "A key that skips a check, a refusal or an approval is authority: "
            "declare it with declare_authority_keys(owner, key) (odoo/tools/"
            "authority_keys.py) so every client door strips it, or carry the "
            "decision server-side (coding_guidelines.rst §10.11).",
        )


class TestAuthorityKeyGateSeesItsFaults(lint_case.LintCase):
    def _found(self, text, declared=frozenset()):
        tree = ast.parse(text)
        return [
            key
            for key, _line in gating_reads(tree)
            if key not in declared and not is_subject_key(key)
        ]

    def test_a_key_that_skips_a_refusal(self):
        text = (
            "def a(self):\n"
            "    if not self.env.context.get('skip_x'):\n"
            "        raise UserError('no')\n"
            "def b(self):\n"
            "    if self._context.get('skip_y'):\n"
            "        return\n"
            "    for r in self:\n"
            "        raise ValidationError('no')\n"
            "def c(self):\n"
            "    if 'force_z' not in self.env.context:\n"
            "        self._check_z()\n"
            "def d(self):\n"
            "    syncing = self.env.context.get('from_sync', False)\n"
            "    if not syncing and self:\n"
            "        self._check_w()\n"
        )
        self.assertEqual(
            self._found(text), ["skip_x", "skip_y", "force_z", "from_sync"]
        )

    def test_what_is_not_a_gating_read(self):
        text = (
            "def a(self):\n"
            "    if self.env.context.get('active_model') != 'x':\n"
            "        raise UserError('no')\n"
            "    if self.env.context.get('default_type'):\n"
            "        raise UserError('no')\n"
            "    if self.env.context.get('sentinel') is SENTINEL:\n"
            "        raise UserError('no')\n"
            "    if self.env.context.get('tracking'):\n"
            "        self.message_post()\n"
            "    if self.env.context.get('declared'):\n"
            "        raise UserError('no')\n"
        )
        self.assertEqual(self._found(text, frozenset({"declared"})), [])

    def test_a_declaration_is_read(self):
        tree = ast.parse("declare_authority_keys('m', 'k1', 'k2')\n")
        self.assertEqual(declared_keys([tree]), {"k1", "k2"})
