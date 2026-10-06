from odoo import fields, models


class WizardAccountMoveTemplateCreateMoveLine(models.TransientModel):
    _name = "wizard.account.move.template.create.move.line"
    _description = "Wizard Lines to generate move from template"
    _inherit = ["mixin.analytic"]
    _order = "sequence, id"

    name = fields.Char(string="Label")
    sequence = fields.Integer()
    display_type = fields.Selection(
        selection=[
            ("product", "Product"),
            ("line_section", "Section"),
            ("line_note", "Note"),
        ],
        default="product",
        required=True,
    )
    quantity = fields.Float(digits="Product Unit")
    price_unit = fields.Float(
        string="Unit Price",
        digits="Product Price",
    )
    discount = fields.Float(
        string="Discount (%)",
        digits="Discount",
    )
    balance = fields.Float(digits="Product Price")
    wizard_id = fields.Many2one(
        comodel_name="wizard.account.move.template.create.move",
        ondelete="cascade",
    )
    template_line_id = fields.Many2one(
        comodel_name="account.move.template.line",
        help="Reference to the original template line",
    )
    partner_id = fields.Many2one(comodel_name="res.partner")
    account_id = fields.Many2one(comodel_name="account.account")
    product_id = fields.Many2one(comodel_name="product.product")
    product_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        string="Unit of Measure",
    )
    tax_ids = fields.Many2many(
        comodel_name="account.tax",
        string="Taxes",
    )
