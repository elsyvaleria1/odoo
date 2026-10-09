/** @odoo-module native */
import { ProductDocumentKanbanController } from "@document_product/js/product_document_kanban/product_document_kanban_controller";
import { patch } from "@web/core/utils/patch";

patch(ProductDocumentKanbanController.prototype, {
    setup() {
        super.setup(...arguments);
        if (this.props.context.eco_bom) {
            this.formData.eco_bom = true;
        }
    },
});
