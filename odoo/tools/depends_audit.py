from __future__ import annotations

import dis
import typing
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from opcode import opmap

from odoo.libs.debug_log import DebugLog

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator

    class _ExceptionTableEntry(typing.Protocol):
        @property
        def start(self) -> int: ...
        @property
        def target(self) -> int: ...
        @property
        def depth(self) -> int: ...
        @property
        def lasti(self) -> bool: ...


_debug = DebugLog(__name__)


def _opnames(*names: str) -> frozenset[str]:
    if missing := sorted(n for n in names if n not in opmap):
        raise RuntimeError(
            f"depends_audit names opcode(s) {', '.join(missing)}, which do not "
            f"exist on this interpreter. Re-derive the sets against it: "
            f"silently dropping one narrows the analysis."
        )
    return frozenset(names)


_FOREIGN_ROOTS = frozenset({"env"})

_NEVER_A_DEPENDENCY = frozenset({"id"})


@dataclass(frozen=True)
class DependsFinding:
    model_name: str
    field_name: str
    reads: tuple[str, ...]
    stored: bool
    declared: tuple[str, ...] = dataclass_field(default=())

    @property
    def label(self) -> str:
        return f"{self.model_name}.{self.field_name}"

    def __str__(self) -> str:
        return (
            f"{self.label} computes without depending on "
            f"{', '.join(self.reads)}"
            f"{' (stored)' if self.stored else ''}"
        )


_LOAD_LOCAL = _opnames("LOAD_FAST", "LOAD_FAST_BORROW", "LOAD_FAST_CHECK")
_LOAD_LOCAL_PAIR = _opnames("LOAD_FAST_LOAD_FAST", "LOAD_FAST_BORROW_LOAD_FAST_BORROW")
_STORE_LOCAL = _opnames("STORE_FAST")
_STORE_LOCAL_PAIR = _opnames("STORE_FAST_STORE_FAST")
_PASS_THROUGH = _opnames("GET_ITER", "UNARY_NOT", "TO_BOOL")
_CALLS = _opnames("CALL", "CALL_KW")
_SUBSCRIPT = 26
_GLOBAL: typing.Final = 2
_SAVED_LOCAL: typing.Final = 3


@dataclass(frozen=True)
class _Function:
    code: typing.Any

    def __bool__(self) -> bool:
        return False


def _scan_load(
    opname: str,
    argval: typing.Any,
    arg: int,
    stack: list[typing.Any],
    pop: Callable[..., list[typing.Any]],
    foreign_locals: set[str],
    names: set[str],
) -> bool:
    if opname in _LOAD_LOCAL:
        stack.append(argval in foreign_locals or argval in _FOREIGN_ROOTS)
    elif opname == "LOAD_FAST_AND_CLEAR":
        stack.append(_SAVED_LOCAL)
    elif opname == "LOAD_CONST" and hasattr(argval, "co_code"):
        stack.append(_Function(argval))
    elif opname == "SET_FUNCTION_ATTRIBUTE":
        function, _attribute = pop(2)[::-1]
        stack.append(function)
    elif opname in _LOAD_LOCAL_PAIR:
        stack.extend(name in foreign_locals for name in argval)
    elif opname == "LOAD_GLOBAL":
        stack.extend([_GLOBAL] * (1 + arg % 2))
    elif opname in ("LOAD_DEREF", "LOAD_NAME"):
        stack.append(argval in _FOREIGN_ROOTS)
    elif opname == "LOAD_ATTR":
        (receiver,) = pop()
        foreign = bool(receiver) or argval in _FOREIGN_ROOTS
        if not foreign and isinstance(argval, str):
            names.add(argval)
        stack.extend([foreign] * (1 + arg % 2))
    elif opname == "STORE_ATTR":
        owner, _value = pop(2)[::-1]
        if not owner and isinstance(argval, str):
            names.add(argval)
    elif opname == "BINARY_OP" and arg == _SUBSCRIPT:
        container, _key = pop(2)
        stack.append(container)
    elif opname == "END_FOR":
        pass
    else:
        return False
    return True


def _scan_call(
    opname: str,
    arg: int,
    keywords: tuple[str, ...],
    stack: list[typing.Any],
    pop: Callable[..., list[typing.Any]],
    foreign_functions: set[typing.Any],
) -> None:
    extra = 1 if opname == "CALL_KW" else 0
    popped = pop(arg + 2 + extra)
    functions = [item for item in popped if isinstance(item, _Function)]
    walked = popped[: 2 + arg - (len(keywords) if extra else 0)]
    if any(item is True for item in walked):
        foreign_functions.update(function.code for function in functions)
    if popped[0] == _GLOBAL:
        arguments = popped[2 : 2 + arg]
        stack.append(all(arguments))
    else:
        stack.append(bool(popped[0] or popped[1]))


def _scan_code(
    bytecode: dis.Bytecode,
    foreign_locals: set[str],
    names: set[str],
    foreign_functions: set[typing.Any],
) -> dict[str, list[typing.Any]]:
    stack: list[typing.Any] = []
    stores: dict[str, list[typing.Any]] = {}

    def pop(count: int = 1) -> list[typing.Any]:
        taken = stack[-count:] if count else []
        del stack[len(stack) - len(taken) :]
        return [False] * (count - len(taken)) + taken

    def store(name: str, value: typing.Any) -> None:
        if value != _SAVED_LOCAL:
            stores.setdefault(name, []).append(value)

    entries: Iterable[_ExceptionTableEntry] = getattr(bytecode, "exception_entries")  # noqa: B009 - Python exposes this table but typeshed omits it
    protected = {entry.start: entry for entry in entries}
    handlers = {entry.target: entry for entry in entries}
    entry_stacks: dict[int, list[typing.Any]] = {}

    keywords: tuple[str, ...] = ()
    for instruction in bytecode:
        if entry := protected.get(instruction.offset):
            entry_stacks[entry.target] = stack[: entry.depth]
        if handler := handlers.get(instruction.offset):
            stack[:] = entry_stacks.get(handler.target, [False] * handler.depth)
            stack.extend([False] * (2 if handler.lasti else 1))
        opname = instruction.opname
        argval = instruction.argval
        arg = instruction.arg or 0
        if _scan_load(opname, argval, arg, stack, pop, foreign_locals, names):
            pass
        elif opname in _CALLS:
            _scan_call(opname, arg, keywords, stack, pop, foreign_functions)
        elif opname in _PASS_THROUGH:
            stack.extend(pop())
        elif opname == "FOR_ITER":
            stack.append(stack[-1] if stack else False)
        elif opname == "UNPACK_SEQUENCE":
            (value,) = pop()
            stack.extend([value] * arg)
        elif opname in _STORE_LOCAL:
            store(argval, *pop())
        elif opname in _STORE_LOCAL_PAIR:
            first, second = pop(2)[::-1]
            store(argval[0], first)
            store(argval[1], second)
        elif opname == "STORE_FAST_LOAD_FAST":
            store(argval[0], *pop())
            stack.append(argval[1] in foreign_locals)
        elif opname == "COPY":
            stack.append(stack[-arg] if len(stack) >= arg else False)
        elif opname == "SWAP":
            if len(stack) >= arg:
                stack[-1], stack[-arg] = stack[-arg], stack[-1]
        else:
            try:
                effect = dis.stack_effect(
                    instruction.opcode, instruction.arg, jump=False
                )
            except ValueError:
                effect = 0
            if effect < 0:
                pop(-effect)
            else:
                stack.extend([False] * effect)
        keywords = (
            argval if opname == "LOAD_CONST" and isinstance(argval, tuple) else ()
        )
    return stores


def _foreign_code_names(
    code: typing.Any, foreign_arguments: bool, foreign_functions: set[typing.Any]
) -> set[str]:
    bytecode = dis.Bytecode(code)
    arguments = (
        set(code.co_varnames[: code.co_argcount]) if foreign_arguments else set()
    )
    foreign_locals = set(arguments)
    for _round in range(8):
        stores = _scan_code(bytecode, foreign_locals, set(), set())
        settled = arguments | {
            name for name, taints in stores.items() if taints and all(taints)
        }
        if settled == foreign_locals:
            break
        foreign_locals = settled
    names: set[str] = set()
    _scan_code(bytecode, foreign_locals, names, foreign_functions)
    return names


def accessed_attribute_names(func: Callable[..., typing.Any]) -> set[str]:
    names: set[str] = set()
    code = getattr(func, "__code__", None)
    if code is None:
        return names
    todo = [(code, False)]
    while todo:
        current, foreign_arguments = todo.pop()
        foreign_functions: set[typing.Any] = set()
        names |= _foreign_code_names(current, foreign_arguments, foreign_functions)
        todo.extend(
            (const, const in foreign_functions)
            for const in current.co_consts
            if hasattr(const, "co_names")
        )
    return names


def _get_functions(
    field: typing.Any, model_class: typing.Any
) -> list[Callable[..., typing.Any]]:
    compute = field.compute
    if not compute:
        return []
    if not isinstance(compute, str):
        return [compute]
    from odoo.orm.fields.base import resolve_mro

    return resolve_mro(model_class, compute, callable)


def audit_field(
    registry: typing.Any, model_class: typing.Any, field: typing.Any
) -> DependsFinding | None:
    functions = _get_functions(field, model_class)
    if not functions:
        return None

    accessed: set[str] = set()
    for function in functions:
        accessed |= accessed_attribute_names(function)

    declared = {path.split(".")[0] for path in registry.field_depends.get(field, ())}
    computed_together = {
        other.name for other in registry.field_computed.get(field, [field])
    }

    reads = (
        (accessed & set(model_class._fields))
        - declared
        - computed_together
        - _NEVER_A_DEPENDENCY
    )
    if not reads:
        return None
    return DependsFinding(
        model_name=field.model_name,
        field_name=field.name,
        reads=tuple(sorted(reads)),
        stored=bool(field.store),
        declared=tuple(sorted(declared)),
    )


def audit_registry(
    registry: typing.Any,
    *,
    only_without_dependencies: bool = True,
    include_stored: bool = False,
) -> Iterator[DependsFinding]:
    registry._get_field_triggers()
    audited = findings = 0
    for model_class in registry.models.values():
        if model_class._abstract:
            continue
        for field in model_class._fields.values():
            if not field.compute:
                continue
            if field.related or field.is_properties:
                continue
            if field.store and not include_stored:
                continue
            if only_without_dependencies and (
                registry.field_depends.get(field)
                or any(
                    key != "access"
                    for key in registry.field_depends_context.get(field, ())
                )
            ):
                continue
            audited += 1
            finding = audit_field(registry, model_class, field)
            if finding is not None:
                findings += 1
                _debug.logic(
                    "depends_audit.finding",
                    model=finding.model_name,
                    field=finding.field_name,
                    reads=finding.reads,
                    stored=finding.stored,
                )
                yield finding
    _debug.pipeline(
        "depends_audit.done",
        models=len(registry.models),
        audited=audited,
        findings=findings,
        only_without_dependencies=only_without_dependencies,
        include_stored=include_stored,
    )
