/** @odoo-module native */
import { useBusSubscription } from "@bus/services/bus_service";
import { Component, markup, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets";

class RefreshSpin extends Component {
    static template = "account_online_synchronization.RefreshSpin";
    static props = { ...standardWidgetProps };
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({
            isHovered: false,
            fetchingStatus: false,
            connectionStateDetails: null,
        });

        this.actionService = useService("action");
        this.orm = useService("orm");
        this.state.fetchingStatus = this.props.record.data.online_sync_fetching_status;

        useBusSubscription("online_sync", (notification) => {
            if (
                notification?.id === this.recordId &&
                notification?.connection_state_details
            ) {
                this.state.connectionStateDetails =
                    notification.connection_state_details;
            }
        });

        onWillStart(() => {
            this._initConnectionStateDetails();
        });
    }

    refresh() {
        this.actionService.restore(this.actionService.currentController.jsId);
    }

    onMouseEnter() {
        this.state.isHovered = true;
    }

    onMouseLeave() {
        this.state.isHovered = false;
    }

    async openAction() {
        const action = await this.orm.call(
            "account.journal",
            "action_view_dashboard_asynchronous_action",
            [this.recordId],
        );
        this.actionService.doAction(action);
        this.state.connectionStateDetails = null;
    }

    async fetchTransactions() {
        this.state.connectionStateDetails = { status: "fetching" };
        const action = await this.orm.call("account.journal", "manual_sync", [
            this.recordId,
        ]);
        if (action) {
            action.help = markup(action.help);
            this.actionService.doAction(action);
        }
    }

    _initConnectionStateDetails() {
        const kanbanDashboardData = JSON.parse(this.props.record.data.kanban_dashboard);
        this.state.connectionStateDetails =
            kanbanDashboardData?.connection_state_details;
    }

    get recordId() {
        return this.props.record.data.id;
    }

    get connectionStatus() {
        return this.state.connectionStateDetails?.status;
    }
}

export const refreshSpin = {
    component: RefreshSpin,
};

registry.category("view_widgets").add("refresh_spin_widget", refreshSpin);
