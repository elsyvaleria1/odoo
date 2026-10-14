import typing

from odoo import fields
from odoo.fields import Domain
from odoo.tools.misc import SENTINEL, Sentinel

if typing.TYPE_CHECKING:
    from odoo.models import BaseModel

NEGATIVE_OPERATORS = {
    "!=": "=",
    "not in": "in",
    "not like": "like",
    "not ilike": "ilike",
}


class ResourceIdentifier(fields.Char):
    identifier_code: str = ""
    through: str = ""

    def __init__(
        self,
        identifier_code: str | Sentinel = SENTINEL,
        through: str | Sentinel = SENTINEL,
        string: str | Sentinel = SENTINEL,
        **kwargs: typing.Any,
    ) -> None:
        super().__init__(
            identifier_code=identifier_code,
            through=through,
            string=string,
            compute=self._compute_identifier,
            inverse=self._inverse_identifier,
            search=self._search_identifier,
            **kwargs,
        )

    def _get_attrs(self, model_class, name: str) -> dict[str, typing.Any]:
        attrs = super()._get_attrs(model_class, name)
        if attrs.get("inherited"):
            return attrs
        attrs.setdefault("store", True)
        attrs.setdefault("readonly", False)
        attrs.setdefault("copy", False)
        code = attrs.get("identifier_code") or self.identifier_code
        if not code:
            raise TypeError(
                f"Field {model_class._name}.{name}: ResourceIdentifier requires "
                "identifier_code."
            )
        through = attrs.get("through") or self.through or ""
        prefix = f"{through}." if through else ""
        attrs.setdefault(
            "_depends",
            (f"{prefix}identifier_ids.value", f"{prefix}identifier_ids.type_id"),
        )
        if attrs.get("store"):
            attrs["search"] = None
        return attrs

    def _get_resource(self, record: BaseModel) -> BaseModel:
        return record.mapped(self.through) if self.through else record

    def _compute_identifier(self, records: BaseModel) -> None:
        for record in records:
            resource = self._get_resource(record)
            record[self.name] = (
                resource.sudo()._get_identifier(self.identifier_code) or False
                if resource
                else False
            )

    def _inverse_identifier(self, records: BaseModel) -> None:
        for record in records:
            resource = self._get_resource(record)
            if resource:
                resource.sudo()._update_identifier(
                    self.identifier_code, record[self.name]
                )

    def _search_identifier(self, records: BaseModel, operator: str, value):
        identifiers = (
            f"{self.through}.identifier_ids" if self.through else "identifier_ids"
        )
        typed = Domain("type_id.code", "=", self.identifier_code)
        positive = NEGATIVE_OPERATORS.get(operator, operator)
        if positive in ("=", "in"):
            wanted = list(value) if positive == "in" else [value]
            values = [item for item in wanted if item]
            domain = (
                Domain(identifiers, "any", typed & Domain("value", "in", values))
                if values
                else Domain.FALSE
            )
            if len(values) != len(wanted):
                domain |= ~Domain(identifiers, "any", typed)
        else:
            domain = Domain(
                identifiers, "any", typed & Domain("value", positive, value)
            )
        return ~domain if operator in NEGATIVE_OPERATORS else domain
