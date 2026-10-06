/** @odoo-module native */
import { Component, proxy, useProps } from "@odoo/owl";
import { useAccountReportContext } from "@report_formula/components/account_report/account_report_context";
import { Dropdown } from "@web/components/dropdown";
import { useService } from "@web/core/utils/hooks";
import { COG_GROUP } from "@web/search/cog_menu/cog_menu_group";
import { CogMenuItem } from "@web/search/cog_menu/cog_menu_item";

export class AccountReportCogMenu extends Component {
    static template = "report_formula.AccountReportCogMenu";
    static components = { CogMenuItem, Dropdown };
    static props = {};
    props = useProps(this.constructor.props);

    setup() {
        this.reportContext = useAccountReportContext();
        this.ui = useService("ui");
        this.controller = proxy(this.reportContext.controller);
    }

    //------------------------------------------------------------------------------------------------------------------
    // Buttons
    //------------------------------------------------------------------------------------------------------------------
    get cogButtons() {
        const buttons = [];

        for (const button of this.controller.buttons) {
            if (!button.always_show) {
                buttons.push({
                    groupNumber: COG_GROUP.APP,
                    ...button,
                    onClick: (ev) => this.controller.buttonAction(ev, button),
                });
            }
        }

        return buttons;
    }
}
