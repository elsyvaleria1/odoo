from odoo import api, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardProductProductReplenish(models.TransientModel):
    _inherit = "wizard.product.product.replenish"

    @api.depends("product_id.bom_ids", "product_id.bom_ids.product_uom_id")
    def _compute_allowed_uom_ids(self):
        super()._compute_allowed_uom_ids()
        for rec in self:
            rec.allowed_uom_ids |= rec.product_id.bom_ids.product_uom_id

    def _get_record_to_notify(self, date):
        order_line = self.env["mrp.production"].search(
            [("write_date", ">=", date), ("product_id", "=", self.product_id.id)],
            order="id desc",
            limit=1,
        )
        return order_line or super()._get_record_to_notify(date)

    def _get_replenishment_order_notification_link(self, production) -> list | None:
        if production._name == "mrp.production":
            return [
                {
                    "label": production.name,
                    "url": f"/odoo/action-mrp.action_mrp_production_form/{production.id}",
                }
            ]
        return super()._get_replenishment_order_notification_link(production)

    def _get_domain_route(self, product_tmpl_id):
        domain = super()._get_domain_route(product_tmpl_id)
        company = product_tmpl_id.company_id or self.env.company
        manufacture_route = (
            self.env["stock.rule"]
            .search([("action", "=", "manufacture"), ("company_id", "=", company.id)])
            .route_id
        )
        if manufacture_route and product_tmpl_id.bom_ids.filtered(
            lambda b: b.type == "normal"
        ):
            _debug.logic(
                "replenish_route_widened",
                template=product_tmpl_id.id,
                route=manufacture_route.id,
            )
            domain = Domain.OR([domain, Domain("id", "in", manufacture_route.ids)])
        return domain
