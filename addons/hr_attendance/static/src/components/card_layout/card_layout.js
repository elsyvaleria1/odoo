/** @odoo-module native */
import { Component, onWillUnmount, proxy, t, useProps } from "@odoo/owl";
import {
    DATE_FULL,
    formatValue,
    now,
    TIME_SIMPLE,
    toLocaleString,
} from "@web/core/l10n/dates";
import { useService } from "@web/core/utils/hooks";

export class CardLayout extends Component {
    static template = "hr_attendance.CardLayout";
    static props = {
        slots: t.object(),
        fromTrialMode: t.boolean().optional(),
        companyImageUrl: t.string(),
        kioskReturn: t.function(),
        activeDisplay: t.string(),
    };
    props = useProps(this.constructor.props);
    setup() {
        this.ui = useService("ui");
        this.state = proxy(this.getDateTime());
        this.timeInterval = setInterval(() => {
            Object.assign(this.state, this.getDateTime());
        }, 1000);
        onWillUnmount(() => {
            clearInterval(this.timeInterval);
        });
    }

    getDateTime() {
        const current = now();
        return {
            dayOfWeek: formatValue(current, "cccc"),
            date: toLocaleString(current, {
                ...DATE_FULL,
                weekday: undefined,
            }),
            time: toLocaleString(current, TIME_SIMPLE),
        };
    }
}
