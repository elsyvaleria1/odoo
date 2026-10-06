from odoo import fields, models


class DocumentsDocument(models.Model):
    _inherit = "document.document"

    def _default_attached_on_mrp(self):
        return (
            "bom"
            if self.env.context.get("eco_bom")
            else super()._default_attached_on_mrp()
        )

    origin_attachment_id = fields.Many2one(
        comodel_name="ir.attachment",
        index="btree_not_null",
    )
    origin_res_model = fields.Char(
        related="origin_attachment_id.res_model",
        string="Origin Model",
    )
    origin_res_name = fields.Char(
        related="origin_attachment_id.res_name",
        string="Origin Name",
    )
