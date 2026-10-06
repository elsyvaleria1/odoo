from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    schedule_count = fields.Integer(
        string="Schedules",
        compute="_compute_schedule_count",
    )

    def _compute_schedule_count(self) -> None:
        grouped_data = self.env["mrp.production.schedule"]._read_group(
            [("product_id.product_tmpl_id", "in", self.ids)],
            ["product_id"],
            ["__count"],
        )
        product_schedule_counts = {product.id: count for product, count in grouped_data}
        for template in self:
            schedule_count = 0
            for product_id in template.product_variant_ids.ids:
                schedule_count += product_schedule_counts.get(product_id, 0)
            template.schedule_count = schedule_count

    def action_view_mps_view(self):
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "mrp_mps.action_mrp_mps"
        )
        action["domain"] = [("product_id.product_tmpl_id", "in", self.ids)]
        return action
