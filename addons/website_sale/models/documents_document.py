from odoo import api, fields, models
from odoo.exceptions import ValidationError


class DocumentsDocument(models.Model):
    _inherit = "document.document"

    shown_on_product_page = fields.Boolean(string="Publish on website")

    @api.constrains("res_model", "shown_on_product_page")
    def _check_product_page_document_model(self) -> None:
        for document in self:
            if (
                document.res_model == "product.product"
                and document.shown_on_product_page
            ):
                raise ValidationError(
                    self.env._(
                        "Documents shown on product page cannot be restricted to a specific variant"
                    )
                )
