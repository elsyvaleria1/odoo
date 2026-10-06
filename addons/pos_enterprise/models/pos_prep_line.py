from odoo import fields, models


class PosPrepLine(models.Model):
    _name = "pos.prep.line"
    _description = "Pos Preparation Line"
    _inherit = ["mixin.pos.load"]

    prep_order_id = fields.Many2one(
        comodel_name="pos.prep.order",
        string="Preparation Order",
        index=True,
        required=True,
        ondelete="cascade",
    )
    quantity = fields.Float(required=True)
    cancelled = fields.Float(string="Quantity of cancelled product")
    pos_order_line_uuid = fields.Char(help="Original pos order line UUID")
    internal_note = fields.Char(help="Internal notes written at the time of the order")
    customer_note = fields.Char(help="Customer notes written at the time of the order")
    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Product ID",
    )
    attribute_value_ids = fields.Many2many(
        comodel_name="product.template.attribute.value",
        relation="pos_prep_line_product_template_attribute_value_rel",
        string="Selected Attributes",
    )
    combo_line_ids = fields.One2many(
        comodel_name="pos.prep.line",
        inverse_name="combo_parent_id",
        string="Combo Lines",
    )
    combo_parent_id = fields.Many2one(
        comodel_name="pos.prep.line",
        string="Parent Combo Line",
        index="btree_not_null",
        help="Indicates the parent line if this is part of a combo",
    )
    pos_order_line_id = fields.Many2one(
        comodel_name="pos.order.line",
        string="Original pos order line",
    )
