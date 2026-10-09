import ast
import datetime
import hashlib
from dataclasses import dataclass

from .types import VALUE_TYPES

ENTRY_POINT = "evaluate"
ENTRY_ARGUMENTS = ("inputs", "rules")
GUARDED_ATTRIBUTE = "_rule_attribute"
GUARDED_MULTIPLY = "_rule_multiply"

HEADER_REQUIRED = ("RULE", "VALID_FROM", "INPUTS", "OUTPUT")
HEADER_OPTIONAL = ("NAME", "VALID_TO", "SOURCES", "EXAMPLES")

SAFE_BUILTIN_NAMES = frozenset(
    {
        "abs",
        "all",
        "any",
        "bool",
        "dict",
        "enumerate",
        "float",
        "int",
        "len",
        "list",
        "max",
        "min",
        "range",
        "round",
        "set",
        "sorted",
        "str",
        "sum",
        "tuple",
        "zip",
    }
)
CALL_KEYWORDS = {
    "sorted": frozenset({"key", "reverse"}),
    "max": frozenset({"key", "default"}),
    "min": frozenset({"key", "default"}),
    "enumerate": frozenset({"start"}),
    "sum": frozenset({"start"}),
}
CONTEXT_HELPERS = frozenset(
    {
        "add_days",
        "add_months",
        "call",
        "call_at",
        "date",
        "end_of_month",
        "round_half_up",
        "weekday",
    }
)
MAX_POWER_EXPONENT = 64

_EXPRESSION_NODES = (
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.IfExp,
    ast.Dict,
    ast.Set,
    ast.List,
    ast.Tuple,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
    ast.comprehension,
    ast.Compare,
    ast.Call,
    ast.keyword,
    ast.Constant,
    ast.Attribute,
    ast.Subscript,
    ast.Slice,
    ast.Name,
    ast.Load,
    ast.Store,
    ast.And,
    ast.Or,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.UAdd,
    ast.USub,
    ast.Not,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Is,
    ast.IsNot,
)
_STATEMENT_NODES = (
    ast.Assign,
    ast.AugAssign,
    ast.If,
    ast.For,
    ast.Return,
    ast.Pass,
    ast.Break,
    ast.Continue,
)
_CONSTANT_TYPES = (int, float, str, bool, type(None))


class RuleSyntaxError(ValueError):
    def __init__(self, message, lineno=None) -> None:
        super().__init__(message if lineno is None else f"line {lineno}: {message}")
        self.lineno = lineno


@dataclass(frozen=True)
class RuleHeader:
    code: str
    name: str
    date_from: datetime.date
    date_to: datetime.date | None
    sources: tuple
    inputs: dict
    output: str
    examples: tuple
    dependencies: tuple
    digest: str


def parse_rule(source: str) -> tuple[RuleHeader, ast.Module]:
    """The header of a rule script and its module, validated against the rule
    grammar and with every attribute read rewritten through the guarded
    accessor. Raises RuleSyntaxError on the first violation."""
    try:
        module = ast.parse(source, mode="exec")
    except SyntaxError as error:
        raise RuleSyntaxError(error.msg, error.lineno) from error
    constants = {}
    entry = None
    for statement in module.body:
        if isinstance(statement, ast.FunctionDef):
            if entry is not None or statement.name != ENTRY_POINT:
                raise RuleSyntaxError(
                    f"a rule defines one function, {ENTRY_POINT}(inputs, rules)",
                    statement.lineno,
                )
            _check_entry_signature(statement)
            entry = statement
        elif (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
        ):
            name = statement.targets[0].id
            if not name.isupper() or name.startswith("_"):
                raise RuleSyntaxError(
                    f"module-level names are UPPERCASE constants, not {name!r}",
                    statement.lineno,
                )
            if name in constants:
                raise RuleSyntaxError(f"{name} is assigned twice", statement.lineno)
            try:
                constants[name] = ast.literal_eval(statement.value)
            except ValueError as error:
                raise RuleSyntaxError(
                    f"{name} must be a literal value", statement.lineno
                ) from error
        else:
            raise RuleSyntaxError(
                "a rule holds only UPPERCASE literal constants and "
                f"{ENTRY_POINT}(inputs, rules)",
                statement.lineno,
            )
    if entry is None:
        raise RuleSyntaxError(f"a rule defines {ENTRY_POINT}(inputs, rules)")
    reserved = frozenset(constants) | SAFE_BUILTIN_NAMES | frozenset(ENTRY_ARGUMENTS)
    validator = _BodyValidator(reserved)
    for statement in entry.body:
        validator.visit(statement)
    header = _read_header(constants, tuple(sorted(validator.dependencies)), source)
    if header.code in validator.dependencies:
        raise RuleSyntaxError(f"{header.code} calls itself")
    _RuntimeGuard().visit(module)
    ast.fix_missing_locations(module)
    return header, module


def _check_entry_signature(function) -> None:
    arguments = function.args
    if (
        function.decorator_list
        or function.returns
        or arguments.posonlyargs
        or arguments.kwonlyargs
        or arguments.vararg
        or arguments.kwarg
        or arguments.defaults
        or tuple(argument.arg for argument in arguments.args) != ENTRY_ARGUMENTS
        or any(argument.annotation for argument in arguments.args)
    ):
        raise RuleSyntaxError(
            f"the signature is exactly {ENTRY_POINT}(inputs, rules)", function.lineno
        )


def _read_header(constants, dependencies, source) -> RuleHeader:
    missing = [name for name in HEADER_REQUIRED if name not in constants]
    if missing:
        raise RuleSyntaxError(f"missing header constants: {', '.join(missing)}")
    code = constants["RULE"]
    if not isinstance(code, str) or not code or code != code.strip():
        raise RuleSyntaxError("RULE is a non-empty dotted code")
    inputs = constants["INPUTS"]
    if not isinstance(inputs, dict) or not all(
        isinstance(name, str) and name.isidentifier() and not name.startswith("_")
        for name in inputs
    ):
        raise RuleSyntaxError("INPUTS maps input names to types")
    unknown = sorted({*inputs.values(), constants["OUTPUT"]} - frozenset(VALUE_TYPES))
    if unknown:
        raise RuleSyntaxError(f"unknown types {unknown}; known: {sorted(VALUE_TYPES)}")
    sources = constants.get("SOURCES", ())
    if isinstance(sources, str):
        sources = (sources,)
    examples = constants.get("EXAMPLES", ())
    if not isinstance(examples, (tuple, list)) or not all(
        isinstance(example, dict) and {"inputs", "expected"} <= example.keys()
        for example in examples
    ):
        raise RuleSyntaxError(
            "EXAMPLES is a tuple of {'inputs': ..., 'expected': ...} dicts"
        )
    return RuleHeader(
        code=code,
        name=constants.get("NAME") or code,
        date_from=_to_date(constants["VALID_FROM"], "VALID_FROM"),
        date_to=_to_date(constants.get("VALID_TO"), "VALID_TO"),
        sources=tuple(sources),
        inputs=dict(inputs),
        output=constants["OUTPUT"],
        examples=tuple(examples),
        dependencies=dependencies,
        digest=hashlib.sha256(source.encode()).hexdigest(),
    )


def _to_date(value, name):
    if value is None:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise RuleSyntaxError(f"{name} is an ISO date string") from error


class _BodyValidator(ast.NodeVisitor):
    def __init__(self, reserved) -> None:
        self.reserved = reserved
        self.dependencies = set()

    def generic_visit(self, node) -> None:
        if not isinstance(node, _EXPRESSION_NODES + _STATEMENT_NODES):
            raise RuleSyntaxError(
                f"{type(node).__name__} is not allowed in a rule",
                getattr(node, "lineno", None),
            )
        super().generic_visit(node)

    def visit_For(self, node) -> None:
        if node.orelse:
            raise RuleSyntaxError("for ... else is not allowed", node.lineno)
        self.generic_visit(node)

    def visit_Constant(self, node) -> None:
        if not isinstance(node.value, _CONSTANT_TYPES):
            raise RuleSyntaxError(
                f"{type(node.value).__name__} constants are not allowed", node.lineno
            )

    def visit_Name(self, node) -> None:
        if node.id.startswith("_"):
            raise RuleSyntaxError(f"names cannot start with _: {node.id}", node.lineno)
        if isinstance(node.ctx, ast.Store) and node.id in self.reserved:
            raise RuleSyntaxError(f"{node.id} cannot be reassigned", node.lineno)

    def visit_Attribute(self, node) -> None:
        if node.attr.startswith("_"):
            raise RuleSyntaxError(
                f"attributes cannot start with _: {node.attr}", node.lineno
            )
        if isinstance(node.ctx, ast.Store):
            raise RuleSyntaxError("attributes cannot be assigned", node.lineno)
        self.generic_visit(node)

    def visit_BinOp(self, node) -> None:
        if isinstance(node.op, ast.Pow) and not (
            isinstance(node.right, ast.Constant)
            and isinstance(node.right.value, (int, float))
            and abs(node.right.value) <= MAX_POWER_EXPONENT
        ):
            raise RuleSyntaxError(
                f"** takes a constant exponent of at most {MAX_POWER_EXPONENT}",
                node.lineno,
            )
        self.generic_visit(node)

    def visit_Call(self, node) -> None:
        function = node.func
        if isinstance(function, ast.Name) and function.id in SAFE_BUILTIN_NAMES:
            allowed = CALL_KEYWORDS.get(function.id, frozenset())
            for keyword in node.keywords:
                if keyword.arg not in allowed:
                    raise RuleSyntaxError(
                        f"{function.id}() takes no keyword {keyword.arg!r}",
                        node.lineno,
                    )
        elif (
            isinstance(function, ast.Attribute)
            and isinstance(function.value, ast.Name)
            and function.value.id == "rules"
            and function.attr in CONTEXT_HELPERS
        ):
            if any(keyword.arg is None for keyword in node.keywords):
                raise RuleSyntaxError("** arguments are not allowed", node.lineno)
            if function.attr in ("call", "call_at"):
                self._record_dependency(node, 0 if function.attr == "call" else 1)
        else:
            raise RuleSyntaxError(
                "a rule calls only the allowed builtins and rules.<helper>()",
                node.lineno,
            )
        for argument in node.args:
            if isinstance(argument, ast.Starred):
                raise RuleSyntaxError("* arguments are not allowed", node.lineno)
            self.visit(argument)
        for keyword in node.keywords:
            self.visit(keyword.value)

    def _record_dependency(self, node, position) -> None:
        if not (
            len(node.args) == position + 1
            and isinstance(node.args[position], ast.Constant)
            and isinstance(node.args[position].value, str)
        ):
            raise RuleSyntaxError(
                "rules.call(code, ...) and rules.call_at(date, code, ...) take "
                "the rule code as a string literal, then keyword inputs",
                node.lineno,
            )
        self.dependencies.add(node.args[position].value)


class _RuntimeGuard(ast.NodeTransformer):
    """Rewrites value.name into _rule_attribute(value, "name"), except the
    rules.<helper> a call names, and a * b into _rule_multiply(a, b), so the
    runtime decides what a read returns and how long a repeated sequence gets."""

    def visit_BinOp(self, node):
        node = self.generic_visit(node)
        if not isinstance(node.op, ast.Mult):
            return node
        return ast.copy_location(
            ast.Call(
                func=ast.Name(id=GUARDED_MULTIPLY, ctx=ast.Load()),
                args=[node.left, node.right],
                keywords=[],
            ),
            node,
        )

    def visit_Call(self, node):
        function = node.func
        if (
            isinstance(function, ast.Attribute)
            and isinstance(function.value, ast.Name)
            and function.value.id == "rules"
        ):
            node.args = [self.visit(argument) for argument in node.args]
            node.keywords = [self.visit(keyword) for keyword in node.keywords]
            return node
        return self.generic_visit(node)

    def visit_Attribute(self, node):
        value = self.visit(node.value)
        return ast.copy_location(
            ast.Call(
                func=ast.Name(id=GUARDED_ATTRIBUTE, ctx=ast.Load()),
                args=[value, ast.Constant(value=node.attr)],
                keywords=[],
            ),
            node,
        )
