from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    version = fields.Integer(
        default=1,
        copy=False,
        help="The current version of the product.",
    )
    eco_count = fields.Integer(
        string="# ECOs",
        compute="_compute_eco_count",
    )
    eco_ids = fields.One2many(
        comodel_name="mrp.eco",
        inverse_name="product_tmpl_id",
        string="ECOs",
    )

    def _compute_eco_count(self) -> None:
        eco_count_map = dict(
            self.env["mrp.eco"]._read_group(
                [("product_tmpl_id", "in", self.ids), ("type", "=", "product")],
                ["product_tmpl_id"],
                ["__count"],
            )
        )
        for product in self:
            product.eco_count = eco_count_map.get(product, 0)

    def mrp_eco_action_product_tmpl(self):
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "mrp_plm.mrp_eco_action_product_tmpl"
        )
        action["domain"] = [
            "&",
            ("product_tmpl_id", "=", self.id),
            ("type", "=", "product"),
        ]
        return action


class ProductProduct(models.Model):
    _inherit = "product.product"

    def mrp_eco_action_product_tmpl(self):
        action = self.product_tmpl_id.mrp_eco_action_product_tmpl()
        action["context"] = {"default_product_tmpl_id": self.product_tmpl_id.id}
        return action
