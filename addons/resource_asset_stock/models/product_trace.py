from odoo import api, fields, models


class ProductTrace(models.Model):
    _inherit = "product.trace"

    asset_ids = fields.One2many(
        comodel_name="resource.resource",
        inverse_name="trace_id",
        string="Assets",
    )
    asset_id = fields.Many2one(
        comodel_name="resource.resource",
        compute="_compute_asset_id",
        search="_search_asset_id",
        compute_sudo=True,
    )

    @api.depends("asset_ids")
    def _compute_asset_id(self) -> None:
        for lot in self:
            lot.asset_id = lot.asset_ids[:1]

    def _search_asset_id(self, operator, value):
        return [("asset_ids", operator, value)]

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
        return assets.with_env(self.env)

    def action_view_asset(self) -> dict:
        self.check_singleton()
        return self.asset_id.get_formview_action()
