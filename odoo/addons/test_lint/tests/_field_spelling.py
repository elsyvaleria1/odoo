import ast
from collections.abc import Iterator
from dataclasses import dataclass

try:
    from ._model_classes import is_field_call
except ImportError:
    from _model_classes import is_field_call  # run as a script, from this directory

__all__ = [
    "FIELD_ATTRIBUTE_ORDER",
    "bound_names",
    "canonical_order",
    "is_field_call",
    "positional_names",
    "spelling_violations",
]


# The positional parameters of each field class's __init__, in order; every
# other class takes the label first. A positional argument is spelled as the
# keyword this table names.
POSITIONAL_PARAMETERS: dict[str, tuple[str, ...]] = {
    "Many2one": ("comodel_name", "string"),
    "One2many": ("comodel_name", "inverse_name", "string"),
    "One2one": ("comodel_name", "inverse_name", "string"),
    "Many2many": ("comodel_name", "relation", "column1", "column2", "string"),
    "Selection": ("selection", "string"),
    "Reference": ("selection", "string"),
    "Count": ("count_of", "string"),
    "Float": ("string", "digits", "min_display_digits"),
    "Monetary": ("string", "currency_field"),
}


_DEFAULT_POSITIONAL = ("string",)


# The order a declaration's keywords are read in: what the field is, what it
# says, its shape, how its value is produced, how it is stored and read, what
# it points at and under which conditions, who tracks it -- then, last of
# all, who may see it and the help text. An attribute the table does not know
# sorts alphabetically before that tail.
FIELD_ATTRIBUTE_ORDER: tuple[str, ...] = (
    "comodel_name",
    "inverse_name",
    "relation",
    "column1",
    "column2",
    "selection",
    "selection_add",
    "related",
    "count_of",
    "model_field",
    "definition",
    "definition_record",
    "definition_record_field",
    "delegate",
    "string",
    "export_string_translation",
    "size",
    "trim",
    "digits",
    "min_display_digits",
    "currency_field",
    "translate",
    "sanitize",
    "sanitize_overridable",
    "sanitize_tags",
    "sanitize_attributes",
    "sanitize_style",
    "sanitize_form",
    "sanitize_conditional_comments",
    "sanitize_output_method",
    "strip_style",
    "strip_classes",
    "attachment",
    "max_width",
    "max_height",
    "verify_resolution",
    "bin_size_field",
    "validate",
    "compute",
    "inverse",
    "search",
    "depends",
    "depends_context",
    "precompute",
    "compute_sudo",
    "related_sudo",
    "recursive",
    "inherited",
    "default",
    "change_default",
    "store",
    "index",
    "copy",
    "readonly",
    "required",
    "prefetch",
    "exportable",
    "company_dependent",
    "config_parameter",
    "aggregator",
    "group_expand",
    "falsy_value",
    "falsy_value_label",
    "domain",
    "context",
    "ondelete",
    "check_company",
    "bypass_search_access",
    "auto_join",
    "tracking",
    "implied_group",
    "write_groups",
    "groups",
    "help",
)


_TAIL: tuple[str, ...] = ("write_groups", "groups", "help")


_RANK = {name: index for index, name in enumerate(FIELD_ATTRIBUTE_ORDER)}


def positional_names(call: ast.Call) -> tuple[str, ...]:
    return POSITIONAL_PARAMETERS.get(call.func.attr, _DEFAULT_POSITIONAL)


def canonical_order(names: list[str]) -> list[str]:
    known = sorted(
        (n for n in names if n in _RANK and n not in _TAIL), key=_RANK.__getitem__
    )
    unknown = sorted(n for n in names if n not in _RANK)
    tail = sorted((n for n in names if n in _TAIL), key=_RANK.__getitem__)
    return known + unknown + tail


@dataclass
class Violation:
    lineno: int
    col_offset: int
    rule: str
    message: str


def bound_names(statement: ast.stmt) -> list[str]:
    match statement:
        case ast.Assign(targets=targets):
            return [t.id for t in targets if isinstance(t, ast.Name)]
        case ast.AnnAssign(target=ast.Name(id=name), value=value) if value is not None:
            return [name]
    return []


def _check_positional(name: str, call: ast.Call) -> Iterator[Violation]:
    if not call.args:
        return
    names = positional_names(call)
    spelled = ", ".join(
        f"{names[i]}=" if i < len(names) else "?"
        for i, arg in enumerate(call.args)
        if not isinstance(arg, ast.Starred)
    )
    yield Violation(
        call.lineno,
        call.col_offset,
        "field-positional-argument",
        f"{name}: {len(call.args)} positional argument(s); spell them as {spelled}",
    )


def _check_layout(name: str, call: ast.Call) -> Iterator[Violation]:
    names = [k.arg for k in call.keywords if k.arg]
    if names != canonical_order(names):
        yield Violation(
            call.lineno,
            call.col_offset,
            "field-attribute-order",
            f"{name}: keywords read {', '.join(names)}; the order is "
            f"{', '.join(canonical_order(names))}",
        )
        return
    if len(call.keywords) < 2:
        return
    lines = [k.lineno for k in call.keywords]
    if len(set(lines)) != len(lines) or lines[0] == call.lineno:
        yield Violation(
            call.lineno,
            call.col_offset,
            "field-attribute-order",
            f"{name}: {len(call.keywords)} keywords share a line; one per line, "
            "none on the line of the call",
        )


def spelling_violations(name: str, call: ast.Call) -> Iterator[Violation]:
    yield from _check_positional(name, call)
    yield from _check_layout(name, call)
