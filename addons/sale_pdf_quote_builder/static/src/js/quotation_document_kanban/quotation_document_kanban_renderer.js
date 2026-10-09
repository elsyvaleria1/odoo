/** @odoo-module native */
import { ProductDocumentKanbanRenderer } from "@document_product/js/product_document_kanban/product_document_kanban_renderer";
import { QuotationDocumentKanbanRecord } from "@sale_pdf_quote_builder/js/quotation_document_kanban/quotation_document_kanban_record";

export class QuotationDocumentKanbanRenderer extends ProductDocumentKanbanRenderer {
    static components = {
        ...ProductDocumentKanbanRenderer.components,
        KanbanRecord: QuotationDocumentKanbanRecord,
    };
}
