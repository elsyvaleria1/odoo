/** @odoo-module native */
import { useService } from "@web/core/utils/hooks";
import { KanbanRenderer } from "@web/views/kanban";

import { ProductCatalogKanbanRecord } from "./kanban_record.js";

export const productCatalogKanbanRendererProps = { ...KanbanRenderer.props };

export class ProductCatalogKanbanRenderer extends KanbanRenderer {
    static props = productCatalogKanbanRendererProps;
    static template = "ProductCatalogKanbanRenderer";
    static components = {
        ...KanbanRenderer.components,
        KanbanRecord: ProductCatalogKanbanRecord,
    };

    setup() {
        super.setup();
        this.action = useService("action");
    }

    get createProductContext() {
        return {};
    }

    get createProductOptions() {
        return { onClose: () => this.props.list.model.load() };
    }

    async createProduct() {
        await this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "product.product",
                target: "new",
                views: [[false, "form"]],
                view_mode: "form",
                context: this.createProductContext,
            },
            this.createProductOptions,
        );
    }
}
