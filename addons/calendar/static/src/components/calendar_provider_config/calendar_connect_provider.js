/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets";

export class CalendarConnectProvider extends Component {
    static props = { ...standardWidgetProps };
    static template = "calendar.CalendarConnectProvider";
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.orm = useService("orm");
    }

    /**
     * Activate the external sync for the first time, after installing the
     * relevant submodule if necessary.
     *
     * @private
     */
    async onConnect(ev) {
        ev.preventDefault();
        ev.stopImmediatePropagation();
        if (!(await this.props.record.save())) {
            return;
        }
        await this.orm.call(
            this.props.record.resModel,
            "action_calendar_prepare_external_provider_sync",
            [this.props.record.resId],
        );
        const provider = this.props.record.data.external_calendar_provider;
        if (!provider) {
            return;
        }
        await this.orm.call("res.users", "calendar_sync_restart", [
            [user.userId],
            provider,
        ]);
        const response = await rpc(`/calendar_sync/${provider}/sync_data`, {
            model: "calendar.event",
            fromurl: window.location.href,
        });
        await this._beforeLeaveContext();
        if (response.status === "need_auth") {
            window.location.assign(response.url);
        } else if (response.status === "need_refresh") {
            window.location.reload();
        }
    }
    /**
     * Hook to perform additional work before redirecting to external url or reloading.
     *
     * @private
     */
    async _beforeLeaveContext() {
        return Promise.resolve();
    }
}

const calendarConnectProvider = {
    component: CalendarConnectProvider,
};
registry
    .category("view_widgets")
    .add("calendar_connect_provider", calendarConnectProvider);
