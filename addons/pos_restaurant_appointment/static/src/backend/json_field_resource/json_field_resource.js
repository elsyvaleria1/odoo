/** @odoo-module native */
import { deserializeDateTime, formatValue } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { JsonField, jsonField } from "@web/fields/basic/json/json_field";

export class JsonFieldResource extends JsonField {
    static template = "pos_restauramt_appointment.JsonFieldResource";

    get timeAndPersonDetails() {
        const formattedValue = JSON.parse(this.formattedValue || "{}");
        if (this.formattedValue) {
            // formattedValue.event_start is the start time in UTC
            const localStartTime = deserializeDateTime(formattedValue.event_start);
            return {
                time: formatValue(localStartTime, "h:mm a"),
                person: formattedValue.capacity,
            };
        } else {
            return false;
        }
    }
}

export const jsonFieldResource = {
    ...jsonField,
    component: JsonFieldResource,
};

registry.category("fields").add("json_field_resource", jsonFieldResource);
