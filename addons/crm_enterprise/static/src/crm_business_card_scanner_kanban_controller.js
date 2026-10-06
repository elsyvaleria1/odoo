/** @odoo-module native */
import { crmKanbanView } from "@crm/views/crm_kanban/crm_kanban_view";
import { isMobileOS } from "@web/core/browser/feature_detection";
import { useService } from "@web/core/utils/hooks";

import { CrmBusinessCardScanner } from "./crm_business_card_scanner.js";

export class CrmBusinessCardScannerKanbanController extends crmKanbanView.Controller {
    static template = "crm_enterprise.CrmBusinessCardScannerKanbanController";

    static components = {
        ...crmKanbanView.Controller.components,
        CrmBusinessCardScanner,
    };

    setup() {
        super.setup();
        this.ui = useService("ui");
        this.isMobileOS = isMobileOS();
    }
}
