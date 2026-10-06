from odoo import api, models
from odoo.libs.debug_log import DebugLog
from odoo.tools import frozendict

_debug = DebugLog(__name__)


class MaintenanceOrder(models.Model):
    _inherit = "maintenance.order"
    _access_anchors = frozendict(
        {
            "user": models.Anchor("user_id", kind="owner"),
        }
    )

    @api.model_create_multi
    def create(self, vals_list):
        default_resources = self.default_get(["resource_ids"]).get("resource_ids", [])
        for vals in vals_list:
            if "block_resource" in vals or "default_block_resource" in self.env.context:
                continue
            resources = self.new(
                {"resource_ids": vals.get("resource_ids", default_resources)}
            ).resource_ids
            if resources and all(resource.asset_id for resource in resources):
                vals["block_resource"] = False
        return super().create(vals_list)

    def _prepare_service_log_vals(self, lot, return_picking):
        vals = super()._prepare_service_log_vals(lot, return_picking)
        # The asset's own product is a vehicle or a machine, and its category
        # types no log, so booking the service against it lands the row in no
        # bucket. The service product is what a maintenance costs.
        service_product = self.env.ref(
            "asset_ledger.product_product_maintenance", raise_if_not_found=False
        )
        vals["product_id"] = service_product.id
        _debug.logic(
            "service_log_product",
            order=self,
            lot=lot,
            product=service_product,
        )
        return vals
