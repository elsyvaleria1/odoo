/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { hasSame, now as currentTime, toLocaleString } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { standardFieldProps } from "@web/fields/standard_field_props";

export class SimpleDateTimeField extends Component {
    static template = "voip.SimpleDateTimeField";
    static props = { ...standardFieldProps };
    props = useProps(this.constructor.props);

    get formattedDate() {
        const dt = this.props.record.data[this.props.name];
        if (!dt) {
            return "";
        }
        const now = currentTime();
        const time = toLocaleString(dt, { hour: "numeric", minute: "2-digit" });

        if (hasSame(dt, now, "day")) {
            return _t("Today, %(time)s", { time });
        }
        const yesterday = now.subtract({ days: 1 });
        if (hasSame(dt, yesterday, "day")) {
            return _t("Yesterday, %(time)s", { time });
        }
        return toLocaleString(dt, {
            month: "numeric",
            day: "2-digit",
            year: "2-digit",
            hour: "numeric",
            minute: "2-digit",
        });
    }
}

export const simpleDateTimeField = {
    component: SimpleDateTimeField,
    displayName: _t("Simple Date & Time"),
    supportedTypes: ["datetime"],
};

registry.category("fields").add("voip_simple_datetime", simpleDateTimeField);
