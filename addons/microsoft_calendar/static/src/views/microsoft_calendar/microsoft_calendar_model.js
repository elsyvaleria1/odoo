/** @odoo-module native */
import { AttendeeCalendarModel } from "@calendar/views/attendee_calendar/attendee_calendar_model";
import { proxy } from "@odoo/owl";
import { rpc } from "@web/core/network";
import { patch } from "@web/core/utils/patch";

patch(AttendeeCalendarModel, {
    services: [...AttendeeCalendarModel.services],
});

patch(AttendeeCalendarModel.prototype, {
    setup(params) {
        super.setup(...arguments);
        this.isAlive = params.isAlive;
        this.microsoftPendingSync = false;
        this.microsoftSync = proxy({ isSync: true, isPaused: false });
    },

    /**
     * @override
     */
    async updateData() {
        if (this.microsoftPendingSync) {
            return super.updateData(...arguments);
        }
        try {
            await Promise.race([
                new Promise((resolve) => setTimeout(resolve, 1000)),
                this.syncMicrosoftCalendar(true),
            ]);
        } catch (error) {
            if (error.event) {
                error.event.preventDefault();
            }
            console.error("Could not synchronize microsoft events now.", error);
            this.microsoftPendingSync = false;
        }
        if (this.isAlive()) {
            return super.updateData(...arguments);
        }
        return new Promise(() => {});
    },

    async syncMicrosoftCalendar(silent = false) {
        this.microsoftPendingSync = true;
        const result = await rpc(
            "/microsoft_calendar/sync_data",
            {
                model: this.resModel,
                fromurl: window.location.href,
            },
            {
                silent,
            },
        );
        if (
            [
                "need_config_from_admin",
                "need_auth",
                "sync_stopped",
                "sync_paused",
            ].includes(result.status)
        ) {
            this.microsoftSync.isSync = false;
        } else if (
            result.status === "no_new_event_from_microsoft" ||
            result.status === "need_refresh"
        ) {
            this.microsoftSync.isSync = true;
        }
        this.microsoftSync.isPaused = result.status === "sync_paused";
        this.microsoftPendingSync = false;
        return result;
    },

    get microsoftIsSync() {
        return this.microsoftSync.isSync;
    },

    get microsoftIsPaused() {
        return this.microsoftSync.isPaused;
    },

    get microsoftCredentialsSet() {
        return this.credentialStatus["microsoft_calendar"] ?? false;
    },
});
