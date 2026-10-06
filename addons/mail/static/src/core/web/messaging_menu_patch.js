// @ts-check
/** @odoo-module native */
import { MessagingMenu } from "@mail/core/public_web/messaging_menu/messaging_menu";
import { makeLogger } from "@web/core/debug/debug_logger";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

const log = makeLogger("mail.messaging_menu");

patch(MessagingMenu.prototype, {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.action = useService("action");
        this.pwa = useService("pwa");
    },
    get canPromptToInstall() {
        return this.pwa.canPromptToInstall;
    },
    get prefixItems() {
        if (!this.showNotificationHubExtras) {
            return super.prefixItems;
        }
        return [
            ...super.prefixItems,
            ...(this.canPromptToInstall ? ["installationRequest"] : []),
            ...this.visibleFailures.map((failure) => failure.localId),
        ];
    },
    get visibleFailures() {
        return this.showNotificationHubExtras ? this.store.failures : [];
    },
    /** @param {import("models").MessagingMenuTab} tab */
    getTabExtraCounter(tab) {
        const extra = super.getTabExtraCounter(tab);
        if (!tab.eq(this.store.messagingMenu.odooBotNotificationsTab)) {
            return extra;
        }
        return extra + (this.canPromptToInstall ? 1 : 0);
    },
    get installationRequest() {
        return {
            body: _t("Come here often? Install the app for quick and easy access!"),
            displayName: _t("Install Odoo"),
            onClick: () => this.pwa.show(),
            iconSrc: this.store.odoobot?.avatarUrl,
            partner: this.store.odoobot,
        };
    },
    /** @param {import("models").Failure} failure */
    onClickFailure(failure) {
        const threadIds = new Set(
            failure.notifications
                .map(({ mail_message_id: message }) => message.thread?.id)
                .filter((id) => id !== undefined),
        );
        log.logic("onClickFailure", () => ({
            type: failure.type,
            resModel: failure.resModel,
            threads: threadIds.size,
        }));
        if (threadIds.size === 1) {
            const message = failure.notifications.find(
                (n) => n.mail_message_id?.thread,
            )?.mail_message_id;
            this.openThread(message.thread);
        } else {
            this.openFailureView(failure);
            this.close();
        }
    },
    /** @param {import("models").Thread} thread */
    openThread(thread) {
        log.logic("openThread", () => ({ thread: thread.localId }));
        thread.open({ focus: true, fromMessagingMenu: true });
        this.close();
    },
    /** @param {import("models").Failure} failure */
    openFailureView(failure) {
        if (failure.type !== "email") {
            return;
        }
        this.action.doAction({
            name: _t("Mail Failures"),
            type: "ir.actions.act_window",
            view_mode: "kanban,list,form",
            views: [
                [false, "kanban"],
                [false, "list"],
                [false, "form"],
            ],
            target: "current",
            res_model: failure.resModel,
            domain: [["message_has_error", "=", true]],
            context: { create: false },
        });
    },
    /**
     * @param {import("models").Failure} failure
     * @returns {Promise<any>}
     */
    cancelNotifications(failure) {
        log.logic("cancelNotifications", () => ({
            type: failure.type,
            resModel: failure.resModel,
            notifications: failure.notifications.length,
        }));
        return this.orm.call(failure.resModel, "notify_cancel_by_type", [], {
            notification_type: failure.type,
        });
    },
    /**
     * @param {import("models").Failure} failure
     * @returns {string}
     */
    getFailureNotificationName(failure) {
        if (failure.type === "email") {
            return _t("Email Failure: %(modelName)s", { modelName: failure.modelName });
        }
        return _t("Failure: %(modelName)s", { modelName: failure.modelName });
    },
});
