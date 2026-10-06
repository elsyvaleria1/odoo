// @ts-check
/** @odoo-module native */
import { isToday } from "@mail/utils/common/dates";
import { useHover } from "@mail/utils/common/hooks";
import { provideMailContext, useMailContext } from "@mail/utils/common/mail_context";
import { Component, t, useProps } from "@odoo/owl";
import { ActionSwiper } from "@web/components/action_swiper";
import {
    DATE_MED,
    DATETIME_SHORT,
    now,
    TIME_SIMPLE,
    toLocaleString,
} from "@web/core/l10n/dates";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";

export const notificationItemProps = {
    counter: t.any().optional(0),
    datetime: t.any().optional(),
    first: t.any().optional(),
    hasMarkAsReadButton: t.any().optional(),
    iconSrc: t.any().optional(),
    important: t.any().optional(),
    muted: t.any().optional(0),
    onClick: t.any(),
    onSwipeLeft: t.any().optional(),
    onSwipeRight: t.any().optional(),
    slots: t.any().optional(),
    isActive: t.any().optional(),
    nameMaxLine: t.any().optional(),
    textMaxLine: t.any().optional(),
    thread: t.any().optional(),
};

export class NotificationItem extends Component {
    static components = { ActionSwiper };
    static props = notificationItemProps;
    static template = "mail.NotificationItem";
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.isToday = isToday;
        this.ui = useService("ui");
        this.store = useService("mail.store");
        this.markAsReadRef = elementRef();
        this.rootRef = elementRef();
        this.rootHover = useHover(this.rootRef);
        provideMailContext({ inNotificationItem: true });
        this.mailContext = useMailContext();
    }

    get attClass() {
        return {
            "o-important": this.props.important,
            "o-interest": this.props.muted === 0,
            "text-muted border-secondary": this.props.muted === 1,
            "opacity-50 border-secondary": this.props.muted === 2,
            "px-3 gap-1 o-small": this.ui.isSmall,
            "border-top-0": this.props.first,
            "o-px-2_5 gap-2": !this.ui.isSmall,
            "o-active": this.props.isActive,
        };
    }

    get dateText() {
        const datetime = this.props.datetime;
        if (!datetime) {
            return undefined;
        }
        if (isToday(datetime)) {
            return toLocaleString(datetime, TIME_SIMPLE);
        }
        if (datetime.year === now().year) {
            return toLocaleString(datetime, { month: "short", day: "numeric" });
        }
        return toLocaleString(datetime, DATE_MED);
    }

    get dateTitle() {
        return this.props.datetime
            ? toLocaleString(this.props.datetime, DATETIME_SHORT)
            : "";
    }

    /** @param {MouseEvent} ev */
    onClick(ev) {
        this.props.onClick(
            this.markAsReadRef.el?.contains(/** @type {Node} */ (ev.target)),
        );
    }
}
