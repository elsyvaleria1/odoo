/** @odoo-module native */
import { Component, proxy, useProps } from "@odoo/owl";
import { formatValue } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets";

class ConnectedUntil extends Component {
    static template = "account_online_synchronization.ConnectedUntil";
    static props = { ...standardWidgetProps };
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({
            isHovered: false,
            displayReconnectButton: false,
        });

        if (this.isConnectionExpiredIn(0)) {
            this.state.displayReconnectButton = true;
        }

        this.action = useService("action");
        this.orm = useService("orm");
    }

    get cssClasses() {
        let cssClasses = "text-nowrap w-100";
        if (this.isConnectionExpiredIn(7)) {
            cssClasses += this.isConnectionExpiredIn(3)
                ? " text-danger"
                : " text-warning";
        }
        return cssClasses;
    }

    onMouseEnter() {
        this.state.isHovered = true;
    }

    onMouseLeave() {
        this.state.isHovered = false;
    }

    get connectedUntilLabel() {
        return formatValue(
            this.props.record.data.expiring_synchronization_date,
            "MMM dd",
        );
    }

    isConnectionExpiredIn(nbDays) {
        return this.props.record.data.expiring_synchronization_due_day <= nbDays;
    }

    async extendConnection() {
        const action = await this.orm.call(
            "account.journal",
            "action_extend_consent",
            [this.props.record.resId],
            {},
        );
        this.action.doAction(action);
    }
}

export const connectedUntil = {
    component: ConnectedUntil,
};

registry.category("view_widgets").add("connected_until_widget", connectedUntil);
