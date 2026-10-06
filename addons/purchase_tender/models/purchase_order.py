from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _name = "purchase.order"
    _inherit = ["mixin.order.tender", "purchase.order"]

    _tender_invite_model = "wizard.purchase.order.invite.vendor"
    _tender_warning_model = "wizard.purchase.order.confirm.open.rival"

    tender_id = fields.Many2one(comodel_name="purchase.tender")
    alternative_po_ids = fields.Many2many(
        comodel_name="purchase.order",
        string="Alternative POs",
        compute="_compute_alternative_po_ids",
        inverse="_inverse_alternative_po_ids",
        domain="[('id', '!=', id), ('state', '=', 'draft')]",
        check_company=True,
        help="The offers of this order's tender, this one included",
    )

    @api.depends("tender_id.order_ids")
    def _compute_alternative_po_ids(self) -> None:
        for order in self:
            order.alternative_po_ids = order.tender_id.order_ids

    def _inverse_alternative_po_ids(self) -> None:
        wanted_by_order = {order: order.alternative_po_ids | order for order in self}
        for order, wanted in wanted_by_order.items():
            current = order.tender_id.order_ids
            if wanted == order and current - order:
                order.tender_id = False
                continue
            (current - wanted).tender_id = False
            added = wanted - current
            if not added:
                continue
            target = order.tender_id or added.tender_id[:1]
            if not target:
                target = order._get_or_create_tender()
            merged = wanted.tender_id - target
            (wanted | merged.order_ids).tender_id = target
            merged.filtered(lambda tender: not tender.order_ids).unlink()

    def action_compare_alternative_lines(self) -> dict:
        ctx = dict(
            self.env.context,
            search_default_groupby_product=True,
            purchase_order_id=self.id,
        )
        view_id = self.env.ref("purchase_tender.purchase_order_line_compare_tree").id
        return {
            "name": self.env._("Compare Order Lines"),
            "type": "ir.actions.act_window",
            "view_mode": "list",
            "res_model": "purchase.order.line",
            "views": [(view_id, "list")],
            "domain": [
                ("order_id", "in", (self | self.alternative_po_ids).ids),
                ("display_type", "=", False),
            ],
            "context": ctx,
        }

    def get_tender_best_lines(self) -> tuple:
        self.check_singleton()
        if not self.tender_id:
            return [], [], []
        best = self.tender_id._get_best_lines()
        return best["best_total"], best["best_date"], best["best_unit"]

    def _merge_alternative_po(self, rfqs):
        if self.alternative_po_ids:
            super()._merge_alternative_po(rfqs)
            self.alternative_po_ids += rfqs.mapped("alternative_po_ids")


class PurchaseOrderLine(models.Model):
    _name = "purchase.order.line"
    _inherit = ["mixin.order.line.tender", "purchase.order.line"]

    price_total_cc = fields.Monetary(
        string="Company Subtotal",
        currency_field="company_currency_id",
        compute="_compute_price_total_cc",
        store=True,
    )
    company_currency_id = fields.Many2one(
        related="company_id.currency_id",
        string="Company Currency",
    )

    @api.depends("price_subtotal", "order_id.currency_rate")
    def _compute_price_total_cc(self) -> None:
        for line in self:
            line.price_total_cc = line.price_subtotal / line.order_id.currency_rate
