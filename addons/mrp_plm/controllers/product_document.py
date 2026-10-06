from odoo.addons.document_product.controllers.document_document import (
    ProductDocumentsController,
)


class ProductDocumentControllerECO(ProductDocumentsController):
    def is_model_valid(self, res_model) -> bool:
        return super().is_model_valid(res_model) or res_model == "mrp.eco"

    def _prepare_additional_document_vals(self, **kwargs):
        super_values = super()._prepare_additional_document_vals(**kwargs)
        if kwargs.get("eco_bom"):
            return super_values | {"attached_on_mrp": "bom"}
        return super_values
