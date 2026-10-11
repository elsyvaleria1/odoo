/** @odoo-module native */
import { useService } from "@web/core/utils/hooks";
import { useViewConfig } from "@web/core/view_config_hooks";
import { ControlPanel } from "@web/search/control_panel/control_panel";

export class AccountReturnCheckControlPanel extends ControlPanel {
    static template = "account.account_return_check_control_panel";

    setup() {
        super.setup();
        this.config = useViewConfig();
        this.ui = useService("ui");
        this.state.embeddedInfos.showEmbedded = true;
        this.state.embeddedInfos.showAllEmbeddedActions = true;
    }
}
