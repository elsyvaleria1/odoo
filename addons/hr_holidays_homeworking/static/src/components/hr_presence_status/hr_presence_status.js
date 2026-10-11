/** @odoo-module native */
import { HrPresenceStatus } from "@hr/components/hr_presence_status/hr_presence_status";
import { HrPresenceStatusPill } from "@hr/components/hr_presence_status_pill/hr_presence_status_pill";
import { HrPresenceStatusPrivate } from "@hr/components/hr_presence_status_private/hr_presence_status_private";
import { HrPresenceStatusPrivatePill } from "@hr/components/hr_presence_status_private_pill/hr_presence_status_private_pill";
import { toLocaleString } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

function onHoliday(component) {
    return Boolean(component.value?.includes("holiday"));
}

function backOn(component, label) {
    const end = component.props.record.data.leave_date_to;
    if (!end) {
        return label;
    }
    return _t("%(label)s, back on %(date)s", {
        label,
        date: toLocaleString(end, { day: "numeric", month: "short", year: "numeric" }),
    });
}

const patchHrPresenceStatus = () => ({
    get color() {
        if (onHoliday(this)) {
            return this.value === "presence_holiday_present"
                ? "text-success"
                : "o_icon_employee_absent";
        }
        return super.color;
    },

    get icon() {
        return onHoliday(this) ? "fa-plane" : super.icon;
    },

    get label() {
        if (!onHoliday(this)) {
            return super.label;
        }
        const option = this.options.find(([value]) => value === this.value);
        return backOn(this, option ? option[1] : "");
    },
});

patch(HrPresenceStatus.prototype, patchHrPresenceStatus());
patch(HrPresenceStatusPrivate.prototype, patchHrPresenceStatus());

const patchHrPresenceStatusPill = () => ({
    get color() {
        if (onHoliday(this)) {
            return this.value === "presence_holiday_present"
                ? "btn-outline-success"
                : "btn-outline-warning";
        }
        return super.color;
    },
});

patch(HrPresenceStatusPill.prototype, patchHrPresenceStatusPill());
patch(HrPresenceStatusPrivatePill.prototype, patchHrPresenceStatusPill());

const patchHrPresenceStatusPrivate = () => ({
    get label() {
        const leave = this.props.record.data.current_leave_id;
        return leave ? backOn(this, leave.display_name) : super.label;
    },
});

patch(HrPresenceStatusPrivate.prototype, patchHrPresenceStatusPrivate());
patch(HrPresenceStatusPrivatePill.prototype, patchHrPresenceStatusPrivate());
