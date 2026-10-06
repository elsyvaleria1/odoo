/** @odoo-module native */
import { AttendeeCalendarModel } from "@calendar/views/attendee_calendar/attendee_calendar_model";
import { proxy } from "@odoo/owl";
import { rpc } from "@web/core/network";
import { user } from "@web/core/user";
import { patch } from "@web/core/utils/patch";

const NOT_SYNCED = [
    "need_config_from_admin",
    "need_auth",
    "sync_stopped",
    "sync_paused",
];
const SYNCED = ["no_new_event", "need_refresh"];

patch(AttendeeCalendarModel.prototype, {
    setup(params) {
        super.setup(...arguments);
        this.isAlive = params.isAlive;
        this.syncProviders = [];
        this.providerSync = {};
    },

    /**
     * @override
     */
    async load() {
        if (!this._syncProvidersLoaded) {
            this.syncProviders = await this.orm.call(
                "res.users",
                "calendar_sync_providers",
                [],
            );
            for (const provider of this.syncProviders) {
                this.providerSync[provider.code] = proxy({
                    isSync: true,
                    isPaused: false,
                    pending: false,
                });
            }
            this._syncProvidersLoaded = true;
        }
        return super.load(...arguments);
    },

    /**
     * @override
     */
    async updateData() {
        const idle = this.syncProviders.filter(
            (provider) => !this.providerSync[provider.code].pending,
        );
        try {
            await Promise.race([
                new Promise((resolve) => setTimeout(resolve, 1000)),
                Promise.all(
                    idle.map((provider) => this.syncCalendar(provider.code, true)),
                ),
            ]);
        } catch (error) {
            if (error.event) {
                error.event.preventDefault();
            }
            console.error("Could not synchronize calendars now.", error);
        }
        if (this.isAlive()) {
            return super.updateData(...arguments);
        }
        return new Promise(() => {});
    },

    async syncCalendar(code, silent = false) {
        const state = this.providerSync[code];
        state.pending = true;
        try {
            const result = await rpc(
                `/calendar_sync/${code}/sync_data`,
                { model: this.resModel, fromurl: window.location.href },
                { silent },
            );
            if (NOT_SYNCED.includes(result.status)) {
                state.isSync = false;
            } else if (SYNCED.includes(result.status)) {
                state.isSync = true;
            }
            state.isPaused = result.status === "sync_paused";
            return result;
        } finally {
            state.pending = false;
        }
    },

    async reloadSyncStatus() {
        this.syncStatus = await this.orm.call(
            "res.users",
            "check_synchronization_status",
            [[user.userId]],
        );
    },

    providerCredentialsSet(provider) {
        return this.credentialStatus?.[provider.key] ?? false;
    },
});
