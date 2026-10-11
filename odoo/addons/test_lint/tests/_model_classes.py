import ast
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

try:
    from . import _ast_index
except ImportError:
    import _ast_index

MODEL_BASES = frozenset({"Model", "AbstractModel", "TransientModel", "BaseModel"})


def literal(node: ast.AST | None):
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def names(node: ast.AST | None) -> tuple[str, ...]:
    value = literal(node)
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(v for v in value if isinstance(v, str))
    return ()


def is_field_call(node: ast.AST | None) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "fields"
        and node.func.attr[:1].isupper()
    )


def keywords(call: ast.Call) -> dict[str, ast.expr]:
    return {keyword.arg: keyword.value for keyword in call.keywords if keyword.arg}


def looks_like_model_class(node: ast.ClassDef) -> bool:
    for base in node.bases:
        match base:
            case ast.Attribute(attr=attr) if attr in MODEL_BASES:
                return True
            case ast.Name(id=name) if name in MODEL_BASES:
                return True
    return False


def class_attributes(node: ast.ClassDef) -> Iterator[tuple[str, ast.expr, ast.stmt]]:
    for statement in node.body:
        match statement:
            case ast.Assign(targets=[ast.Name(id=name)], value=value):
                yield name, value, statement
            case ast.AnnAssign(target=ast.Name(id=name), value=value) if value:
                yield name, value, statement


def inherited(node: ast.ClassDef) -> tuple[str, ...]:
    for name, value, _statement in class_attributes(node):
        if name == "_inherit":
            return names(value)
    return ()


def field_declarations(node: ast.ClassDef) -> Iterator[tuple[str, ast.Call, ast.stmt]]:
    for name, value, statement in class_attributes(node):
        if not name.startswith("_") and is_field_call(value):
            yield name, value, statement


@dataclass(frozen=True)
class Constraint:
    attribute: str
    text: str
    lineno: int
    is_index: bool


@dataclass
class ModelClass:
    model: str
    parents: tuple[str, ...] = ()
    fields: dict[str, frozenset[str]] = field(default_factory=dict)
    constraints: list[Constraint] = field(default_factory=list)


def _constraint(name: str, value: ast.expr, statement: ast.stmt) -> Constraint | None:
    if not (isinstance(value, ast.Call) and value.args):
        return None
    kind = value.func.attr if isinstance(value.func, ast.Attribute) else None
    text = literal(value.args[0])
    if kind not in ("Constraint", "UniqueIndex") or not isinstance(text, str):
        return None
    return Constraint(name, text, statement.lineno, kind == "UniqueIndex")


def collect(tree: ast.Module) -> list[ModelClass]:
    out = []
    for node in _ast_index.nodes(tree):
        if not (isinstance(node, ast.ClassDef) and looks_like_model_class(node)):
            continue
        declared = model_names = ()
        constraints = []
        for name, value, statement in class_attributes(node):
            if name == "_name":
                model_names = names(value)
            elif name == "_inherit":
                declared = names(value)
            elif constraint := _constraint(name, value, statement):
                constraints.append(constraint)
        model = model_names[0] if model_names else (declared[0] if declared else None)
        if not model:
            continue
        out.append(
            ModelClass(
                model,
                tuple(p for p in declared if p != model) if model_names else (),
                {
                    name: frozenset(
                        key
                        for key, value in keywords(call).items()
                        if literal(value) is True
                    )
                    for name, call, _statement in field_declarations(node)
                },
                constraints,
            )
        )
    return out


def fold(classes: Iterable[ModelClass], keyword: str) -> dict[str, dict[str, bool]]:
    own: dict[str, dict[str, bool]] = {}
    parents: dict[str, set[str]] = {}
    for model_class in classes:
        bucket = own.setdefault(model_class.model, {})
        for name, flags in model_class.fields.items():
            bucket[name] = bucket.get(name, False) or keyword in flags
        parents.setdefault(model_class.model, set()).update(model_class.parents)
    changed = True
    while changed:
        changed = False
        for model, fields_ in own.items():
            for parent in parents.get(model, ()):
                for name, flag in own.get(parent, {}).items():
                    merged = fields_.get(name, False) or flag
                    if fields_.get(name) != merged:
                        fields_[name] = merged
                        changed = True
    return own
