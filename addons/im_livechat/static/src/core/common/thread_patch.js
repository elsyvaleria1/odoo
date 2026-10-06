/** @odoo-module native */
import { Thread } from "@mail/core/common/thread";
import { toUserLangString } from "@mail/utils/common/dates";
import { hasSame, now, TIME_SIMPLE } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { patch } from "@web/core/utils/patch";

patch(Thread.prototype, {
    setup() {
        super.setup(...arguments);
        this.IM_STATUS_DELAY = 1500;
        Object.assign(this.state, { isVisitorOffline: false });
        useLayoutEffect(
            () => {
                if (!this.props.thread.livechatVisitorMember?.im_status) {
                    return;
                }
                clearTimeout(this.imStatusTimeoutId);
                if (
                    this.props.thread.livechatVisitorMember.im_status.includes(
                        "offline",
                    )
                ) {
                    this.imStatusTimeoutId = setTimeout(
                        () => (this.state.isVisitorOffline = true),
                        this.IM_STATUS_DELAY,
                    );
                } else {
                    this.state.isVisitorOffline = false;
                }
                return () => clearTimeout(this.imStatusTimeoutId);
            },
            () => [this.props.thread.livechatVisitorMember?.im_status],
        );
    },
    get showVisitorDisconnected() {
        return (
            this.store.self.notEq(this.props.thread.livechatVisitorMember?.persona) &&
            !this.props.thread.livechat_end_dt &&
            this.props.thread.livechatVisitorMember &&
            this.state.isVisitorOffline
        );
    },
    get disconnectedText() {
        const offlineSince =
            this.props.thread.livechatVisitorMember.persona.offline_since;
        if (!offlineSince) {
            return _t("Visitor is disconnected");
        }
        if (hasSame(offlineSince, now(), "day")) {
            return _t("Visitor is disconnected since %(time)s", {
                time: toUserLangString(offlineSince, TIME_SIMPLE),
            });
        }
        if (hasSame(offlineSince, now().subtract({ days: 1 }), "day")) {
            return _t("Visitor is disconnected since yesterday at %(time)s", {
                time: toUserLangString(offlineSince, TIME_SIMPLE),
            });
        }
        return _t("Visitor is disconnected");
    },
});
