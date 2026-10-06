/** @odoo-module native */
import { ProductCatalogKanbanRenderer } from "@product/product_catalog/kanban_renderer";
import { productCatalogKanbanView } from "@product/product_catalog/kanban_view";
import { registry } from "@web/core/registry";

import { FSMProductCatalogKanbanController } from "./kanban_controller.js";
import { FSMProductCatalogKanbanModel } from "./kanban_model.js";
import { FSMProductCatalogKanbanRecord } from "./kanban_record.js";

export class FSMProductCatalogKanbanRenderer extends ProductCatalogKanbanRenderer {
    static components = {
        ...ProductCatalogKanbanRenderer.components,
        KanbanRecord: FSMProductCatalogKanbanRecord,
    };

    get createProductContext() {
        return { default_invoice_policy: "delivery" };
    }
}

export const fsmProductCatalogKanbanView = {
    ...productCatalogKanbanView,
    Renderer: FSMProductCatalogKanbanRenderer,
    Controller: FSMProductCatalogKanbanController,
    Model: FSMProductCatalogKanbanModel,
    buttonTemplate: "industry_fsm_sale.FSMProductCatalogKanbanController.Buttons",
};

registry.category("views").add("fsm_product_kanban", fsmProductCatalogKanbanView);
