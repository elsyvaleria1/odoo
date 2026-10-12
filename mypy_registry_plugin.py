from __future__ import annotations

import keyword
import re
from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from mypy.nodes import (
    AssignmentStmt,
    ClassDef,
    Expression,
    ListExpr,
    MypyFile,
    NameExpr,
    PlaceholderNode,
    StrExpr,
    TupleExpr,
    TypeInfo,
    Var,
)
from mypy.plugin import AttributeContext, ClassDefContext, MethodContext, Plugin
from mypy.server.trigger import make_trigger, make_wildcard_trigger
from mypy.typeops import make_simplified_union
from mypy.types import (
    AnyType,
    Instance,
    LiteralType,
    Type,
    TypeOfAny,
    UnionType,
    get_proper_type,
)

if TYPE_CHECKING:
    from mypy.checker import TypeChecker

STUB_MODULE = "odoo_registry_stubs"
ENVIRONMENT_GETITEM = "odoo.orm.runtime.environment.Environment.__getitem__"
BASE_MODEL = "odoo.orm.models.base.BaseModel"
TRAVERSAL_MIXIN = "odoo.orm.models.mixins.traversal.TraversalMixin"
ENVIRONMENT_RECORDS = {
    "odoo.orm.runtime.environment.Environment.user": "res.users",
    "odoo.orm.runtime.environment.Environment.company": "res.company",
    "odoo.orm.runtime.environment.Environment.companies": "res.company",
}
RESERVED_CLASSES = frozenset(
    ("Any", "BaseModel", "Environment", "Generic", "Literal", "TypeVar")
)


def stub_class_name(model_name: str) -> str:
    parts = re.split(r"[._]", model_name)
    name = "".join(part[:1].upper() + part[1:] for part in parts if part)
    if (
        not name
        or not name[0].isalpha()
        or keyword.iskeyword(name)
        or name in RESERVED_CLASSES
    ):
        name = "Model" + name
    return name


def _strings(expr: Expression) -> list[str] | None:
    if isinstance(expr, StrExpr):
        return [expr.value]
    if isinstance(expr, ListExpr | TupleExpr):
        values = [item.value for item in expr.items if isinstance(item, StrExpr)]
        return values if len(values) == len(expr.items) else None
    return None


def _model_name(defn: ClassDef) -> str | None:
    declared: dict[str, list[str] | None] = {}
    for stmt in defn.defs.body:
        if not isinstance(stmt, AssignmentStmt) or len(stmt.lvalues) != 1:
            continue
        target = stmt.lvalues[0]
        if isinstance(target, NameExpr) and target.name in ("_name", "_inherit"):
            declared[target.name] = _strings(stmt.rvalue)
    names = declared.get("_name") or declared.get("_inherit")
    return names[0] if names else None


def _registry_stub(info: TypeInfo) -> TypeInfo | None:
    return next(
        (base for base in info.mro if base.fullname.startswith(f"{STUB_MODULE}.")),
        None,
    )


def _literal_strings(ctx: MethodContext) -> list[str] | None:
    if not ctx.args or not ctx.args[0]:
        return None
    expr = ctx.args[0][0]
    if isinstance(expr, StrExpr):
        return [expr.value]
    arg_type = get_proper_type(ctx.arg_types[0][0]) if ctx.arg_types[0] else None
    alternatives = arg_type.items if isinstance(arg_type, UnionType) else [arg_type]
    names = []
    for alternative in alternatives:
        literal = get_proper_type(alternative)
        if isinstance(literal, Instance) and literal.last_known_value is not None:
            literal = literal.last_known_value
        if not isinstance(literal, LiteralType) or not isinstance(literal.value, str):
            return None
        names.append(literal.value)
    return names


class RegistryStubsPlugin(Plugin):
    def _add_registry_dependencies(self, ctx: MethodContext) -> None:
        api = cast("TypeChecker", ctx.api)
        for trigger in (
            make_trigger(STUB_MODULE),
            make_wildcard_trigger(STUB_MODULE),
            make_trigger(f"{STUB_MODULE}.Environment.__getitem__"),
        ):
            api.tree.plugin_deps.setdefault(trigger, set()).add(
                api.tscope.current_target()
            )

    def _registry_classes(self, ctx: MethodContext) -> dict[str, TypeInfo]:
        self._add_registry_dependencies(ctx)
        api = cast("TypeChecker", ctx.api)
        classes: dict[str, TypeInfo] = {}
        module = api.modules.get(STUB_MODULE)
        for symbol in module.names.values() if module is not None else ():
            info = symbol.node
            if not isinstance(info, TypeInfo):
                continue
            name = info.names.get("_name")
            literal = get_proper_type(name.type) if name is not None else None
            if isinstance(literal, LiteralType) and isinstance(literal.value, str):
                classes[literal.value] = info
        return classes

    def _typed_model(self, ctx: MethodContext) -> Type:
        model_names = _literal_strings(ctx)
        if model_names is None:
            return ctx.default_return_type
        classes = self._registry_classes(ctx)
        if not classes:
            ctx.api.fail(
                "No generated registry model types were loaded; run odoo-bin stubs "
                "and add the output directory to MYPYPATH",
                ctx.context,
            )
            return ctx.default_return_type
        result: list[Type] = []
        for model_name in model_names:
            info = classes.get(model_name)
            if info is None:
                ctx.api.fail(
                    f"Model {model_name!r} is absent from the generated registry; "
                    "check the name or regenerate the stubs after installing its addon",
                    ctx.context,
                )
                result.append(ctx.default_return_type)
            else:
                result.append(Instance(info, []))
        return make_simplified_union(result)

    def _mapped_path(self, ctx: MethodContext, receiver: Instance, path: str) -> Type:
        if not path:
            return receiver
        value: Type = receiver
        api = cast("TypeChecker", ctx.api)
        for name in path.split("."):
            current = get_proper_type(value)
            if isinstance(current, AnyType):
                return current
            if not isinstance(current, Instance) or not current.type.has_base(
                BASE_MODEL
            ):
                ctx.api.fail(
                    f"Cannot traverse non-relational field in mapped({path!r})",
                    ctx.context,
                )
                return AnyType(TypeOfAny.from_error)
            stub = _registry_stub(current.type)
            if stub is None:
                return AnyType(TypeOfAny.special_form)
            trigger = make_trigger(f"{stub.fullname}.{name}")
            api.tree.plugin_deps.setdefault(trigger, set()).add(
                api.tscope.current_target()
            )
            symbol = stub.names.get(name)
            descriptor = get_proper_type(symbol.type) if symbol is not None else None
            if (
                not isinstance(descriptor, Instance)
                or descriptor.type.fullname != f"{STUB_MODULE}._F"
            ):
                ctx.api.fail(f"Unknown field {name!r} in mapped({path!r})", ctx.context)
                return AnyType(TypeOfAny.from_error)
            value = descriptor.args[0]
        proper = get_proper_type(value)
        if isinstance(proper, Instance) and proper.type.has_base(BASE_MODEL):
            return value
        return ctx.api.named_generic_type("builtins.list", [value])

    def _typed_mapped(self, ctx: MethodContext) -> Type:
        receiver = get_proper_type(ctx.type)
        if not isinstance(receiver, Instance):
            return ctx.default_return_type
        owner = receiver.type.get_containing_type_info("mapped")
        if owner is None or owner.fullname != TRAVERSAL_MIXIN:
            return ctx.default_return_type
        self._add_registry_dependencies(ctx)
        paths = _literal_strings(ctx)
        if paths is not None:
            return make_simplified_union(
                [self._mapped_path(ctx, receiver, path) for path in paths]
            )
        argument = (
            get_proper_type(ctx.arg_types[0][0])
            if ctx.arg_types and ctx.arg_types[0]
            else None
        )
        if isinstance(argument, Instance) and argument.type.fullname == "builtins.str":
            return AnyType(TypeOfAny.special_form)
        result = get_proper_type(ctx.default_return_type)
        if isinstance(result, Instance) and result.type.fullname == "builtins.list":
            item = get_proper_type(result.args[0])
            if isinstance(item, UnionType) and any(
                isinstance(member := get_proper_type(part), Instance)
                and member.type.has_base(BASE_MODEL)
                for part in item.items
            ):
                return AnyType(TypeOfAny.special_form)
            if isinstance(item, AnyType) or (
                isinstance(item, Instance) and item.type.has_base(BASE_MODEL)
            ):
                return item
        return ctx.default_return_type

    def _attach_registry_model(self, ctx: ClassDefContext) -> None:
        info = ctx.cls.info
        if info.fullname.startswith(f"{STUB_MODULE}.") or not info.has_base(BASE_MODEL):
            return
        model_name = _model_name(ctx.cls)
        if model_name is None:
            return
        symbol = ctx.api.lookup_fully_qualified_or_none(
            f"{STUB_MODULE}.{stub_class_name(model_name)}"
        )
        stub = symbol.node if symbol is not None else None
        if isinstance(stub, PlaceholderNode) and not ctx.api.final_iteration:
            ctx.api.defer()
            return
        if isinstance(stub, TypeInfo) and stub not in info.mro:
            info.mro = [info, stub, *info.mro[1:]]

    def _release_declared_fields(self, ctx: ClassDefContext) -> None:
        info = ctx.cls.info
        stub = _registry_stub(info)
        if stub is None or stub is info:
            return
        for name, symbol in info.names.items():
            if isinstance(symbol.node, Var) and name in stub.names:
                symbol.node.allow_incompatible_override = True

    def _registry_field(self, name: str, ctx: AttributeContext) -> Type:
        receiver = get_proper_type(ctx.type)
        if ctx.is_lvalue or not isinstance(receiver, Instance):
            return ctx.default_attr_type
        stub = _registry_stub(receiver.type)
        symbol = stub.names.get(name) if stub is not None else None
        node = symbol.node if symbol is not None else None
        declared = (
            get_proper_type(node.type)
            if isinstance(node, Var) and node.type is not None
            else None
        )
        if (
            isinstance(declared, Instance)
            and declared.type.fullname == f"{STUB_MODULE}._F"
            and declared.args
        ):
            return declared.args[0]
        return ctx.default_attr_type

    def _environment_record(self, model_name: str, ctx: AttributeContext) -> Type:
        if ctx.is_lvalue:
            return ctx.default_attr_type
        module = cast("TypeChecker", ctx.api).modules.get(STUB_MODULE)
        symbol = (
            module.names.get(stub_class_name(model_name))
            if module is not None
            else None
        )
        if symbol is None or not isinstance(symbol.node, TypeInfo):
            return ctx.default_attr_type
        return Instance(symbol.node, [])

    def get_customize_class_mro_hook(
        self, fullname: str
    ) -> Callable[[ClassDefContext], None] | None:
        return self._attach_registry_model

    def get_base_class_hook(
        self, fullname: str
    ) -> Callable[[ClassDefContext], None] | None:
        return self._release_declared_fields

    def get_attribute_hook(
        self, fullname: str
    ) -> Callable[[AttributeContext], Type] | None:
        model_name = ENVIRONMENT_RECORDS.get(fullname)
        if model_name is not None:
            return lambda ctx: self._environment_record(model_name, ctx)
        name = fullname.rpartition(".")[2]
        return lambda ctx: self._registry_field(name, ctx)

    def get_additional_deps(self, file: MypyFile) -> list[tuple[int, str, int]]:
        if file.fullname == STUB_MODULE or file.fullname.startswith("mypy."):
            return []
        return [(10, STUB_MODULE, -1)]

    def get_method_hook(self, fullname: str) -> Callable[[MethodContext], Type] | None:
        if fullname == ENVIRONMENT_GETITEM:
            return self._typed_model
        if fullname.endswith(".mapped"):
            return self._typed_mapped
        return None


def plugin(version: str) -> type[Plugin]:
    return RegistryStubsPlugin
