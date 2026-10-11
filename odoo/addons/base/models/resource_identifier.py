import re
from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ResourceIdentifier(models.Model):
    _name = "resource.identifier"
    _description = "Resource Identifier"
    _order = "type_id, id"
    _rec_name = "value"

    resource_id = fields.Many2one(
        comodel_name="resource.resource",
        index=True,
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        related="resource_id.company_id",
    )
    type_id = fields.Many2one(
        comodel_name="resource.identifier.type",
        index=True,
        required=True,
        ondelete="restrict",
    )
    value = fields.Char(required=True)
    normalized_value = fields.Char(
        compute="_compute_normalized_value",
        store=True,
        index="btree_not_null",
    )
    valid_until = fields.Date()

    _type_value_idx = models.Index("(type_id, normalized_value)")
    _resource_type_uniq = models.Constraint(
        "UNIQUE(resource_id, type_id)",
        "A resource carries one value per identifier type.",
    )

    @api.constrains("value", "type_id")
    def _check_pattern(self) -> None:
        for identifier in self:
            pattern = identifier.type_id.pattern
            if pattern and not re.fullmatch(pattern, identifier.normalized_value or ""):
                _debug.logic(
                    "identifier.refused", reason="pattern", identifier=identifier
                )
                raise ValidationError(
                    self.env._(
                        "%(value)s is not a valid %(type)s.",
                        value=identifier.value,
                        type=identifier.type_id.name,
                    )
                )

    @api.constrains("normalized_value", "type_id", "resource_id", "company_id")
    def _check_unique(self) -> None:
        candidates = self.filtered(
            lambda i: i.normalized_value and i.type_id.unique_scope != "none"
        )
        if not candidates:
            return
        others = self.sudo().search(
            Domain("id", "not in", candidates.ids)
            & Domain("type_id", "in", candidates.type_id.ids)
            & Domain("normalized_value", "in", candidates.mapped("normalized_value"))
        )
        taken = defaultdict(self.env["resource.identifier"].sudo)
        for other in others:
            taken[(other.type_id.id, other.normalized_value)] |= other
        for identifier in candidates:
            holders = taken[(identifier.type_id.id, identifier.normalized_value)]
            if identifier.type_id.unique_scope == "company":
                holders = holders.filtered_domain(
                    [("resource_id.company_id", "=", identifier.company_id.id)]
                )
            holders = holders.filtered_domain(
                [("resource_id", "!=", identifier.resource_id.id)]
            )
            if holders:
                _debug.logic(
                    "identifier.refused", reason="duplicate", identifier=identifier
                )
                raise ValidationError(
                    self.env._(
                        "%(type)s %(value)s already identifies %(resource)s.",
                        type=identifier.type_id.name,
                        value=identifier.value,
                        resource=holders[0].resource_id.display_name,
                    )
                )

    @api.depends("value")
    def _compute_normalized_value(self) -> None:
        normalize = self.env["resource.identifier.type"]._normalize
        for identifier in self:
            identifier.normalized_value = normalize(identifier.value)

    @api.model
    def _search_display_name(self, operator, value):
        domain = super()._search_display_name(operator, value)
        if not operator.endswith("like") or not isinstance(value, str):
            return domain
        normalized = self.env["resource.identifier.type"]._normalize(value)
        if not normalized:
            return domain
        by_normalized = Domain("normalized_value", operator, normalized)
        if operator in Domain.NEGATIVE_OPERATORS:
            return Domain(domain) & by_normalized
        return Domain(domain) | by_normalized

    @api.depends("type_id.name", "value")
    def _compute_display_name(self):
        for identifier in self:
            identifier.display_name = f"{identifier.type_id.name}: {identifier.value}"
