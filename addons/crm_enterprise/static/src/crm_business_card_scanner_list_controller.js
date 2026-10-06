/** @odoo-module native */
import { isMobileOS } from "@web/core/browser/feature_detection";
import { useDialogContext } from "@web/core/dialog_context_hooks";
import { useService } from "@web/core/utils/hooks";
import { ListController } from "@web/views/list";

import { CrmBusinessCardScanner } from "./crm_business_card_scanner.js";

export class CrmBusinessCardScannerListController extends ListController {
    static template = "crm_enterprise.CrmBusinessCardScannerListController";

    static components = {
        ...ListController.components,
        CrmBusinessCardScanner,
    };

    setup() {
        super.setup();
        this.dialogContext = useDialogContext();
        this.ui = useService("ui");
        this.isMobileOS = isMobileOS();
    }
}
