/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets";

class IAPActionButtonsWidget extends Component {
    static template = "iap.ActionButtonsWidget";
    static props = {
        ...standardWidgetProps,
        serviceName: t.string(),
        showServiceButtons: t.boolean(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
    }

    async onViewServicesClicked() {
        this.action.doAction("iap.iap_account_action");
    }

    async onManageServiceLinkClicked() {
        const account_id = await this.orm.silent.call("iap.account", "get_account_id", [
            this.props.serviceName,
        ]);
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "iap.account",
            res_id: account_id,
            views: [[false, "form"]],
        });
    }
}

export const iapActionButtonsWidget = {
    component: IAPActionButtonsWidget,
    extractProps: ({ attrs }) => ({
        serviceName: attrs.service_name,
        showServiceButtons: attrs.hide_service !== "1",
    }),
};
registry.category("view_widgets").add("iap_buy_more_credits", iapActionButtonsWidget);
