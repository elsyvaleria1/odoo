/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { Dropdown, DropdownItem } from "@web/components/dropdown";
import {
    compareDates,
    dateTime,
    DATETIME_MED,
    now,
    toLocaleString,
} from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";

export const FOREVER = dateTime({ year: 9999, month: 12, day: 31 }, "UTC");

export class DndSelector extends Component {
    static components = { Dropdown, DropdownItem };
    static template = "voip.DndSelector";
    static props = {};
    props = useProps(this.constructor.props);

    setup() {
        this.settings = useService("mail.store").settings;
    }

    get badgeTitle() {
        if (this.isAvailable) {
            return _t("Available");
        }
        if (this.isMutedForever) {
            return _t("Do Not Disturb until I turn it back on");
        }
        return _t("Do Not Disturb until %(time)s", {
            time: toLocaleString(this.doNotDisturbUntilDt, DATETIME_MED),
        });
    }

    get doNotDisturbUntilDt() {
        return this.settings.do_not_disturb_until_dt;
    }

    get dndButtonBottomText() {
        if (this.isAvailable) {
            return _t("Incoming calls will be muted");
        }
        if (this.isMutedForever) {
            return _t("Until I turn it back on");
        }
        return _t("Until %(time)s", {
            time: toLocaleString(this.doNotDisturbUntilDt, DATETIME_MED),
        });
    }

    get isAvailable() {
        return (
            !this.doNotDisturbUntilDt ||
            compareDates(this.doNotDisturbUntilDt, now()) <= 0
        );
    }

    get isMutedForever() {
        return (
            this.doNotDisturbUntilDt &&
            this.doNotDisturbUntilDt.epochMilliseconds === FOREVER.epochMilliseconds
        );
    }

    get statusText() {
        if (this.isAvailable) {
            return _t("Available");
        }
        return _t("Do Not Disturb");
    }
}
