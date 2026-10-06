// @ts-check
/** @odoo-module native */
import { useRegisterMessageRef } from "@mail/utils/common/hooks";
import { useMailContext } from "@mail/utils/common/mail_context";
import { Component, t, useProps } from "@odoo/owl";
import { dateSettings } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { escape } from "@web/core/utils/format/strings";
import { useService } from "@web/core/utils/hooks";
export class NotificationMessage extends Component {
    static template = "mail.NotificationMessage";
    static props = {
        message: t.any(),
        thread: t.any(),
        registerMessageRef: t.any().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.mailContext = useMailContext();
        this.rootRef = elementRef();
        this.root = useRegisterMessageRef(this.rootRef);
        this.escape = escape;
        this.store = useService("mail.store");
        this.linkNavigation = useService("mail.link_navigation");
    }

    /** @param {MouseEvent} ev */
    async onClickNotificationMessage(ev) {
        this.linkNavigation.handleClickOnLink(ev, this.props.thread);
        const { oeType, oeId } = /** @type {HTMLElement} */ (ev.target).dataset;
        if (oeType === "highlight") {
            await this.mailContext.messageHighlight?.highlightMessage(
                this.store["mail.message"].insert({
                    id: Number(oeId),
                    res_id: this.props.thread.id,
                    model: this.props.thread.model,
                    thread: this.props.thread,
                }),
                this.props.thread,
            );
        }
    }

    get message() {
        return this.props.message;
    }

    get callInformation() {
        const history = this.message.call_history_ids[0];
        if (history?.duration_hour === undefined || !history?.end_dt) {
            return _t("%(author)s started a call.", {
                author: this.message.authorName,
            });
        }
        const totalSeconds = Math.max(1, Math.round(history.duration_hour * 3600));
        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = hours || minutes ? 0 : totalSeconds % 60;
        const { locale, numberingSystem } = dateSettings;
        /** @type {Array<[string, number]>} */
        const amounts = [
            ["hour", hours],
            ["minute", minutes],
            ["second", seconds],
        ];
        const parts = amounts
            .filter(([, amount]) => amount !== 0)
            .map(([unit, amount]) =>
                new Intl.NumberFormat(locale, {
                    useGrouping: false,
                    style: "unit",
                    unitDisplay: "short",
                    unit,
                    numberingSystem,
                }).format(amount),
            );
        return _t("Call lasted %(duration)s.", {
            duration: new Intl.ListFormat(locale, {
                type: "conjunction",
                style: "narrow",
            }).format(parts),
        });
    }
}
