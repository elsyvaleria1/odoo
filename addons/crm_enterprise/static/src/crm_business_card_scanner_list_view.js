/** @odoo-module native */
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list";

import { CrmBusinessCardScannerListController } from "./crm_business_card_scanner_list_controller.js";

export const CrmBusinessCardsScannerListView = {
    ...listView,
    Controller: CrmBusinessCardScannerListController,
};

registry
    .category("views")
    .add("crm_business_cards_scanner_list", CrmBusinessCardsScannerListView);
