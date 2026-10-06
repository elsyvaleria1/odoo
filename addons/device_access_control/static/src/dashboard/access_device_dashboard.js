/** @odoo-module native */
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { parseISO, userTimeZone } from "@web/core/l10n/dates";
import { toRelative } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions";

class AccessDeviceDashboard extends Component {
    static template = "device_access_control.AccessDeviceDashboard";
    static props = { ...standardActionServiceProps };
    props = useProps(this.constructor.props);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = proxy({
            devices: [],
            stats: {},
            loading: true,
        });

        onWillStart(async () => {
            await this.loadDashboardData();
        });
    }

    async loadDashboardData() {
        this.state.loading = true;
        const data = await this.orm.call(
            "device.device",
            "get_access_dashboard_data",
            [],
        );
        this.state.devices = data.devices;
        this.state.stats = data.stats;
        this.state.loading = false;
    }

    getStateLabel(state) {
        const map = {
            connected: "Online",
            disconnected: "Offline",
            error: "Error",
        };
        return map[state] || state;
    }

    getDoorIcon(doorState) {
        const map = {
            open: "fa-unlock text-success",
            closed: "fa-lock text-muted",
            always_open: "fa-unlock-alt text-warning",
            always_closed: "fa-ban text-danger",
            unknown: "fa-question-circle text-muted",
        };
        return map[doorState] || "fa-question-circle text-muted";
    }

    getDoorLabel(doorState) {
        const map = {
            open: "Open",
            closed: "Closed",
            always_open: "Always Open",
            always_closed: "Locked",
            unknown: "Unknown",
        };
        return map[doorState] || doorState;
    }

    formatTime(isoString) {
        if (!isoString) {
            return "";
        }
        const date = parseISO(isoString, "UTC")?.withTimeZone(userTimeZone());
        return date ? toRelative(date) : null;
    }

    async _deviceAction(deviceId, method, successMsg, successType = "info") {
        try {
            await this.orm.call("device.device", method, [deviceId]);
            this.notification.add(successMsg, { type: successType });
        } catch (e) {
            const msg = e.data?.message || e.message || "Unknown error";
            this.notification.add(msg, { type: "danger", sticky: true });
        }
        await this.loadDashboardData();
    }

    async onOpenDoor(deviceId) {
        await this._deviceAction(
            deviceId,
            "action_view_door",
            "Door opened successfully.",
            "success",
        );
    }

    async onCloseDoor(deviceId) {
        await this._deviceAction(deviceId, "action_close_door", "Door closed.");
    }

    async onLockDoor(deviceId) {
        await this._deviceAction(
            deviceId,
            "action_always_close",
            "Door locked.",
            "warning",
        );
    }

    async onCheckConnection(deviceId) {
        await this._deviceAction(
            deviceId,
            "action_check_connection",
            "Connection checked.",
        );
    }

    onViewUsers(deviceId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Device Users",
            res_model: "access.device.user",
            view_mode: "list,form",
            views: [
                [false, "list"],
                [false, "form"],
            ],
            domain: [["device_id", "=", deviceId]],
            context: { default_device_id: deviceId },
        });
    }

    onAddDevice() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "device.device",
            views: [[false, "form"]],
            context: { default_device_category_id: false },
        });
    }

    onViewEvents() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Access Events",
            res_model: "access.event",
            view_mode: "list,form",
            views: [
                [false, "list"],
                [false, "form"],
            ],
        });
    }

    async onRefresh() {
        await this.loadDashboardData();
    }
}

registry.category("actions").add("access_device_dashboard", AccessDeviceDashboard);
