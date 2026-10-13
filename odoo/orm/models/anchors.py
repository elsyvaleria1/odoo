from __future__ import annotations

import typing
from dataclasses import dataclass

from ..helpers import get_domain_companies_parent_of, get_domain_company_parent_of

if typing.TYPE_CHECKING:
    from collections.abc import Mapping

    from ..fields.base import Field
    from .base import BaseModel

ANCHOR_KINDS: Mapping[str, str] = {
    "company": "res.company",
    "owner": "res.users",
    "creator": "res.users",
    "employee": "hr.employee",
    "team": "team.team",
    "unit": "hr.department",
    "partner": "res.partner",
}
HIERARCHIES = frozenset({"parent_of", "child_of"})


@dataclass(frozen=True, slots=True)
class Anchor:
    path: str
    kind: str | None = None
    shared: bool | None = None
    hierarchy: str | None = None
    usage: str | None = None


def collect_anchors(model_cls: type[BaseModel]) -> dict[str, Anchor]:
    declared: dict[str, str | Anchor] = {}
    for cls in reversed(model_cls.mro()):
        declared.update(vars(cls).get("_access_anchors") or {})
    anchors: dict[str, Anchor] = {}
    for key, value in declared.items():
        anchor = Anchor(value) if isinstance(value, str) else value
        kind = anchor.kind or key
        if kind not in ANCHOR_KINDS:
            raise TypeError(
                f"{model_cls._name}: anchor {key!r} has no kind; name one of "
                f"{sorted(ANCHOR_KINDS)} with kind=..."
            )
        if anchor.hierarchy and (
            anchor.hierarchy not in HIERARCHIES or kind != "company"
        ):
            raise TypeError(
                f"{model_cls._name}: anchor {key!r} reads a hierarchy "
                f"{anchor.hierarchy!r}; only a company anchor reads parent_of or "
                f"child_of"
            )
        if anchor.usage is not None and kind != "team":
            raise TypeError(
                f"{model_cls._name}: anchor {key!r} names a usage; only a team "
                f"anchor has one"
            )
        if anchor.path:
            anchors[key] = Anchor(
                anchor.path, kind, anchor.shared, anchor.hierarchy, anchor.usage
            )
    creator = model_cls._fields.get("create_uid")
    if (
        "creator" not in declared
        and creator is not None
        and creator.comodel_name == "res.users"
    ):
        anchors["creator"] = Anchor("create_uid", "creator")
    if "company" not in declared:
        if model_cls._name == "res.company":
            anchors["company"] = Anchor("id", "company")
        else:
            for name in ("company_id", "company_ids"):
                field = model_cls._fields.get(name)
                if (
                    field is not None
                    and field.comodel_name == "res.company"
                    and (field.store or field.related or field.search)
                ):
                    anchors["company"] = Anchor(name, "company")
                    break
    return anchors


def infer_company_variant(
    model_cls: type[BaseModel], anchor: Anchor, models: Mapping[str, type[BaseModel]]
) -> Anchor:
    if anchor.kind != "company":
        return Anchor(
            anchor.path,
            anchor.kind,
            bool(anchor.shared),
            anchor.hierarchy or "",
            anchor.usage,
        )
    shared = anchor.shared
    if shared is None:
        shared = not all(
            field.required for field in path_fields(model_cls, anchor.path, models)
        )
    hierarchy = anchor.hierarchy
    if hierarchy is None:
        check = getattr(model_cls, "_get_domain_company_compatible", None)
        parent_of = (get_domain_company_parent_of, get_domain_companies_parent_of)
        hierarchy = "parent_of" if check in parent_of else ""
    return Anchor(anchor.path, anchor.kind, shared, hierarchy, anchor.usage)


def path_fields(
    model_cls: type[BaseModel], path: str, models: Mapping[str, type[BaseModel]]
) -> list[Field[typing.Any]]:
    if path == "id":
        return []
    fields: list[Field[typing.Any]] = []
    current = model_cls
    for name in path.split("."):
        field = current._fields.get(name)
        if field is None:
            break
        fields.append(field)
        if not field.comodel_name or field.comodel_name not in models:
            break
        current = models[field._get_comodel_name()]
    return fields


def anchor_path_error(
    model_cls: type[BaseModel],
    key: str,
    anchor: Anchor,
    models: Mapping[str, type[BaseModel]],
) -> str | None:
    target = ANCHOR_KINDS[anchor.kind or key]
    if anchor.path == "id":
        if model_cls._name != target:
            return f"its path 'id' is a {model_cls._name}, not a {target}"
        return None
    current = model_cls
    for name in anchor.path.split("."):
        field = current._fields.get(name)
        if field is None:
            return f"{current._name}.{name} does not exist"
        if not (field.store or field.related or field.search):
            return f"{field} is neither stored nor searchable"
        if not field.relational:
            return f"{field} is not relational"
        if field.comodel_name is None or field.comodel_name not in models:
            return f"{field} leads to {field.comodel_name}, which is not loaded"
        current = models[field.comodel_name]
    reached = current._name
    if reached != target:
        return f"its path leads to {reached}, not to {target}"
    return None
