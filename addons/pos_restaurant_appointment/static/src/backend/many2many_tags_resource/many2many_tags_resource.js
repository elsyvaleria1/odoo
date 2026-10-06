/** @odoo-module native */
import { t } from "@odoo/owl";
import {
    compareDates,
    deserializeDateTime,
    serializeDateTime,
} from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import {
    Many2ManyTagsField,
    many2ManyTagsField,
} from "@web/fields/relational/many2many_tags";
import { Many2XAutocomplete } from "@web/fields/relational/many2x_autocomplete";

export class FieldMany2ManyTagsResourceMany2XAutocomplete extends Many2XAutocomplete {
    static template =
        "pos_restaurant_appointment.FieldMany2ManyTagsResourceMany2XAutocomplete";
    static components = {
        ...Many2XAutocomplete.components,
    };
    static props = {
        ...Many2XAutocomplete.props,
        event_start_time: t.object().optional(),
        event_end_time: t.object().optional(),
    };

    setup() {
        super.setup();
        this.ui = useService("ui");
    }

    getPeopleCount(record) {
        if (record.is_used) {
            const localStartTime = deserializeDateTime(record.is_used.event_start);
            const localEndTime = deserializeDateTime(record.is_used.event_stop);
            const eventStart = this.props.event_start_time;
            const eventEnd = this.props.event_end_time;
            return eventStart &&
                eventEnd &&
                compareDates(localStartTime, eventEnd) < 0 &&
                compareDates(localEndTime, eventStart) > 0
                ? record.is_used.capacity
                : "";
        }
        return "";
    }
}

export class FieldMany2ManyTagsResource extends Many2ManyTagsField {
    static template = "pos_restaurant_appointment.FieldMany2ManyTagsResource";
    static components = {
        ...Many2ManyTagsField.components,
        Many2XAutocomplete: FieldMany2ManyTagsResourceMany2XAutocomplete,
    };

    get context() {
        const context = this.props.context || {};
        const jsDate = this.props.record.data.start;
        context["start_date"] = jsDate ? serializeDateTime(jsDate) : null;
        return context;
    }

    get specification() {
        return {
            is_used: {},
        };
    }
}

export const fieldMany2ManyTagsResource = {
    ...many2ManyTagsField,
    component: FieldMany2ManyTagsResource,
};

registry.category("fields").add("many2many_tags_resource", fieldMany2ManyTagsResource);
