/** @odoo-module native */
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
        this.busService = useService("bus_service");
        this.orm = useService("orm");
        this.state.fetchingStatus = this.props.record.data.online_sync_fetching_status;

        this.busService.subscribe("online_sync", (notification) => {
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

    /**
     * Open the action stored on the database by the asynchronous process, so users
     * trigger it when they want instead of when the process ends.
     */
    async openAction() {
        const action = await this.orm.call(
            "account.journal",
            "action_view_dashboard_asynchronous_action",
            [this.recordId],
        );
        this.actionService.doAction(action);
        this.state.connectionStateDetails = null;
    }

    /**
     * Request a transaction fetch. Nothing follows in the usual case, as websockets
     * update the status on their own; an action is only returned when the Odoo Fin
     * iframe must be opened to refresh the connection.
     */
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

    /**
     * Restore the last connection state, if any, from the kanban dashboard data.
     */
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
