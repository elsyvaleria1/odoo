from odoo import fields, models


class SaleCommissionPlanAchievement(models.Model):
    _name = "sale.commission.plan.achievement"
    _description = "Commission Plan Achievement"
    _order = "id"

    plan_id = fields.Many2one(
        comodel_name="sale.commission.plan",
        index=True,
        required=True,
        ondelete="cascade",
    )

    type = fields.Selection(
        selection=[
            ("amount_invoiced", "Amount Invoiced"),
            ("amount_sold", "Amount Sold"),
            ("qty_invoiced", "Quantity Invoiced"),
            ("qty_sold", "Quantity Sold"),
        ],
        index=True,
        required=True,
    )

    product_id = fields.Many2one(comodel_name="product.product")
    product_categ_id = fields.Many2one(
        comodel_name="product.category",
        string="Category",
    )

    rate = fields.Float(
        default=lambda self: 1 if self.plan_id.type == "target" else 0.05,
        required=True,
    )

    def _compute_display_name(self):
        for record in self:
            product_name = record.product_id.name or ""
            product_categ_id_name = record.product_categ_id.name or ""
            labels = dict(self._fields["type"]._description_selection(self.env))
            record_type = self.env._("%s", record.type and labels[record.type]) or ""
            record.display_name = self.env._(
                "%(plan)s - %(type)s %(product)s %(categ)s",
                plan=record.plan_id.name,
                type=record_type,
                product=product_name,
                categ=product_categ_id_name,
            )
