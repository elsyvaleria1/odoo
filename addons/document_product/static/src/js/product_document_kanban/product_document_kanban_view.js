/** @odoo-module native */
import { ProductDocumentKanbanController } from "@document_product/js/product_document_kanban/product_document_kanban_controller";
import { ProductDocumentKanbanRenderer } from "@document_product/js/product_document_kanban/product_document_kanban_renderer";
import { registry } from "@web/core/registry";
import { kanbanView } from "@web/views/kanban";

export const productDocumentKanbanView = {
    ...kanbanView,
    Controller: ProductDocumentKanbanController,
    Renderer: ProductDocumentKanbanRenderer,
    buttonTemplate: "document_product.ProductDocumentKanbanView.Buttons",
};

registry.category("views").add("product_documents_kanban", productDocumentKanbanView);
