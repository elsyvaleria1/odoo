from odoo import api, fields, models


class ProductTrace(models.Model):
    _inherit = "product.trace"

    asset_id = fields.Many2one(
        comodel_name="resource.resource",
        compute="_compute_asset_id",
        store=True,
        index="btree_not_null",
        copy=False,
        readonly=False,
    )

    _asset_uniq = models.UniqueIndex(
        "(asset_id) WHERE asset_id IS NOT NULL", "A lot is one asset at most."
    )

    @api.depends("product_id.asset_kind_id")
    def _compute_asset_id(self) -> None:
        for lot in self:
            lot.asset_id = lot.asset_id

    @api.model_create_multi
    def create(self, vals_list):
        lots = super().create(vals_list)
        lots.filtered(
            lambda lot: lot.product_id.asset_kind_id and not lot.asset_id
        )._create_asset()
        return lots

    def _prepare_asset_vals(self):
        self.check_singleton()
        return {
            "name": f"{self.product_id.name} {self.name}",
            "product_id": self.product_id.id,
            "kind_id": self.product_id.asset_kind_id.id,
            "company_id": self.company_id.id,
            "trace_id": self.id,
        }

    def _create_asset(self):
        if not self:
            return self.env["resource.resource"]
        assets = (
            self.env["resource.resource"]
            .sudo()
            .create([lot._prepare_asset_vals() for lot in self])
        )
        for lot, asset in zip(self, assets, strict=True):
            lot.sudo().asset_id = asset
        return assets.with_env(self.env)

    def action_view_asset(self) -> dict:
        self.check_singleton()
        return self.asset_id.get_formview_action()
