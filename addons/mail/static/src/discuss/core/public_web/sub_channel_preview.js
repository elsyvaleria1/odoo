// @ts-check
/** @odoo-module native */
import { isToday } from "@mail/utils/common/dates";
import { useMailContext } from "@mail/utils/common/mail_context";
import { Component, t, useProps } from "@odoo/owl";
import { DATE_MED, TIME_SIMPLE, toLocaleString } from "@web/core/l10n/dates";

export class SubChannelPreview extends Component {
    static template = "mail.SubChannelPreview";
    static props = {
        class: t.any().optional(),
        onClick: t.any().optional(),
        thread: t.any(),
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.mailContext = useMailContext();
    }

    /**
     * @param {import("models").Message} message
     * @returns {string|undefined}
     */
    dateText(message) {
        const datetime = message.datetime;
        if (!datetime) {
            return undefined;
        }
        if (isToday(datetime)) {
            return toLocaleString(datetime, TIME_SIMPLE);
        }
        return toLocaleString(datetime, DATE_MED);
    }

    get thread() {
        return this.props.thread;
    }

    onClick() {
        this.props.onClick?.();
    }
}
