from typing import Any

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import OrderedSet


class Documents(models.Model):
    _inherit = "document.document"

    asset_id = fields.Many2one(
        comodel_name="resource.resource",
        compute="_compute_asset_id",
        search="_search_asset_id",
        help="The asset this document is attached to",
    )

    @api.depends("res_id", "res_model")
    def _compute_asset_id(self) -> None:
        asset_model = self.env["resource.resource"]
        reference = asset_model._get_reference_model_name()
        filed = self.filtered(lambda d: d.res_model == reference and d.res_id)
        asset_ids = set(
            asset_model.with_context(active_test=False)
            .search([("id", "in", filed.mapped("res_id")), ("kind_id", "!=", False)])
            .ids
        )
        for document in self:
            document.asset_id = (
                document in filed
                and document.res_id in asset_ids
                and asset_model.browse(document.res_id)
            )

    @api.model
    def _search_asset_id(self, operator: str, value: Any) -> Domain:
        lot = self.env["resource.resource"]
        reference = lot._get_reference_model_name()
        things = Domain("kind_id", "!=", False)
        if operator == "in":
            values = list(value)
            sentinels = []
            if any(v is True for v in values):
                sentinels.append(Domain("asset_id", "not in", [False]))
            if any(v is False for v in values):
                sentinels.append(
                    Domain("res_model", "!=", reference)
                    | Domain("res_id", "not in", lot._search(things))
                )
            value = OrderedSet(v for v in values if not isinstance(v, bool))
            if sentinels:
                return Domain.OR([*sentinels, self._search_asset_id(operator, value)])
            query_model = lot._search(
                things
                & Domain.OR(
                    Domain(
                        lot._rec_name if isinstance(v, str) else "id",
                        operator,
                        v,
                    )
                    for v in value
                    if v
                ),
            )
        elif operator == "any" and isinstance(value, Domain):
            query_model = lot._search(things & value)
        elif operator.endswith("like") and not operator.startswith("not"):
            query_model = lot._search(things & Domain(lot._rec_name, operator, value))
        else:
            return NotImplemented
        return (
            Domain.FALSE
            if query_model.is_empty()
            else Domain("res_id", "in", query_model)
        ) & Domain("res_model", "=", reference)
