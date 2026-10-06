import ast
from collections import defaultdict

from . import _production_python, lint_case

_VALUE_KINDS = frozenset(
    {"str", "int", "float", "bytes", "dict", "list", "tuple", "set", "frozenset"}
)


def _members(annotation: ast.expr) -> list[ast.expr]:
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        return _members(annotation.left) + _members(annotation.right)
    return [annotation]


def _base_name(member: ast.expr) -> str | None:
    if isinstance(member, ast.Subscript):
        member = member.value
    if isinstance(member, ast.Name):
        return member.id
    if isinstance(member, ast.Attribute):
        return member.attr
    if isinstance(member, ast.Constant) and member.value is None:
        return "None"
    return None


def _is_literal_false(member: ast.expr) -> bool:
    return (
        isinstance(member, ast.Subscript)
        and _base_name(member.value) == "Literal"
        and isinstance(member.slice, ast.Constant)
        and member.slice.value is False
    )


def _answers_bool(function: ast.FunctionDef) -> bool:
    if function.returns is not None and any(
        _base_name(member) == "bool" or _is_literal_false(member)
        for member in _members(function.returns)
    ):
        return True
    pending = list(function.body)
    while pending:
        node = pending.pop()
        if isinstance(
            node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda | ast.ClassDef
        ):
            continue
        if (
            isinstance(node, ast.Return)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, bool)
        ):
            return True
        pending.extend(ast.iter_child_nodes(node))
    return False


_KINDS = ("mixed_value_kinds", "false_sentinel", "bool_or_none", "action_bool_result")


def _contracts(tree: ast.Module) -> list[tuple[str, str]]:
    # (kind, "<line> <what>") of every retired contract the file declares
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name.startswith("action_") and _answers_bool(node):
            found.append(("action_bool_result", f"{node.lineno} {node.name}"))
        if node.returns is None:
            continue
        members = _members(node.returns)
        if len(members) < 2:
            continue
        names = [_base_name(member) for member in members]
        where = f"{node.lineno} {node.name} -> {ast.unparse(node.returns)}"
        if len(_VALUE_KINDS.intersection(names)) >= 2:
            found.append(("mixed_value_kinds", where))
        if any(_is_literal_false(member) for member in members):
            found.append(("false_sentinel", where))
        if "bool" in names and "None" in names:
            found.append(("bool_or_none", where))
    return found


def return_contract_findings(sources) -> dict[str, dict[str, list[str]]]:
    found: dict[str, dict[str, list[str]]] = {
        kind: defaultdict(list) for kind in _KINDS
    }
    by_path = _production_python.extract(_contracts, (path for *_, path in sources))
    for repo, _module, path in sources:
        for kind, where in by_path[path] or ():
            found[kind][repo].append(f"{path}:{where}")
    return found


class TestReturnContracts(lint_case.LintCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sources = _production_python.production_sources()
        cls.found = return_contract_findings(cls.sources)

    def _ratchet(self, kind: str, gate: str, what: str, fix: str) -> None:
        self.assert_ratchet_per_repository(
            self.found[kind], gate, f"{what} in <repo>", fix
        )

    def test_mixed_value_kinds_only_go_down(self):
        self._ratchet(
            "mixed_value_kinds",
            "return_mixed_value_kinds",
            "method(s) annotated to return different kinds of value",
            "A name has one return contract (§2.4.23): split the method, or "
            "return a NamedTuple, dataclass, TypedDict or Enum.",
        )

    def test_false_sentinel_only_goes_down(self):
        self._ratchet(
            "false_sentinel",
            "return_false_sentinel",
            "method(s) annotated to return a value or False",
            "Absence is None or the empty value of the type (§2.4.23); False "
            "stays only where the ORM defines it, a field read.",
        )

    def test_bool_or_none_only_goes_down(self):
        self._ratchet(
            "bool_or_none",
            "return_bool_or_none",
            "method(s) annotated bool | None",
            "Yes, no and unknown is an Enum, not a tri-state bool (§2.4.23).",
        )

    def test_action_bool_result_only_goes_down(self):
        self._ratchet(
            "action_bool_result",
            "return_action_bool_result",
            "public action method(s) answering a bool",
            "An action returns the client action to run, or None (§2.4.23): "
            "success is the absence of an exception, not True.",
        )
