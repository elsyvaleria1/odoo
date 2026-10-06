/** @odoo-module native */
import { AttendeeCalendarController } from "@calendar/views/attendee_calendar/attendee_calendar_controller";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { AlertDialog, ConfirmationDialog } from "@web/ui/dialog";

patch(AttendeeCalendarController.prototype, {
    setup() {
        super.setup(...arguments);
        this.dialog = useService("dialog");
    },

    get activeSyncProvider() {
        return this.model.syncProviders.find(
            (provider) =>
                this.model.providerCredentialsSet(provider) &&
                this.model.syncStatus?.[provider.key] === "sync_active",
        );
    },

    get pausedSyncProvider() {
        return this.model.syncProviders.find(
            (provider) => this.model.syncStatus?.[provider.key] === "sync_paused",
        );
    },

    get anySyncProviderConfigured() {
        return this.model.syncProviders.some((provider) =>
            this.model.providerCredentialsSet(provider),
        );
    },

    isSyncOffered(provider) {
        const state = this.model.providerSync[provider.code];
        return (
            this.model.providerCredentialsSet(provider) &&
            !state.isSync &&
            !state.isPaused
        );
    },

    async onSyncCalendar(provider) {
        await this.orm.call("res.users", "calendar_sync_restart", [
            [user.userId],
            provider.code,
        ]);
        const syncResult = await this.model.syncCalendar(provider.code);
        if (syncResult.status === "need_auth") {
            window.location.assign(syncResult.url);
        } else if (syncResult.status === "need_config_from_admin") {
            if (this.isSystemUser) {
                this.dialog.add(ConfirmationDialog, {
                    title: _t("Configuration"),
                    body: _t(
                        "The %s Synchronization needs to be configured before you can use it, do you want to do it now?",
                        provider.label,
                    ),
                    confirm: this.actionService.doAction.bind(
                        this.actionService,
                        syncResult.action,
                    ),
                    confirmLabel: _t("Configure"),
                    cancel: () => {},
                    cancelLabel: _t("Discard"),
                });
            } else {
                this.dialog.add(AlertDialog, {
                    title: _t("Configuration"),
                    body: _t(
                        "An administrator needs to configure %s Synchronization before you can use it!",
                        provider.label,
                    ),
                });
            }
        } else {
            await this.model.reloadSyncStatus();
            await this.model.load();
        }
    },

    async onStopSynchronization(provider) {
        await this.orm.call("res.users", "calendar_sync_stop", [
            [user.userId],
            provider.code,
        ]);
        await this.model.reloadSyncStatus();
        await this.model.load();
    },
});
