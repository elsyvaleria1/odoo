from odoo import api, fields, models

from .resource_asset import DOCUMENT_LINKS


class ProductTrace(models.Model):
    _inherit = "product.trace"

    fuel_card_id = fields.Many2one(
        related="asset_id.fuel_card_id",
        readonly=False,
    )
    highway_pass_id = fields.Many2one(
        related="asset_id.highway_pass_id",
        readonly=False,
    )
    property_deed_id = fields.Many2one(
        related="asset_id.property_deed_id",
        readonly=False,
    )
    lease_agreement_id = fields.Many2one(
        related="asset_id.lease_agreement_id",
        readonly=False,
    )
    building_permit_id = fields.Many2one(
        related="asset_id.building_permit_id",
        readonly=False,
    )

    @api.model
    def _asset_ledger_field_map(self):
        return super()._asset_ledger_field_map() | {n: n for n in DOCUMENT_LINKS}

    def action_view_documents(self):
        self.check_singleton()
        return self.asset_id.action_view_documents() if self.asset_id else True
