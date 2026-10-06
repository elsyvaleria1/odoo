// @ts-check
/** @odoo-module native */

import { registerField } from "@web/fields/_registry";

import { CardPropertiesField } from "./card_properties_field.js";
import { propertiesField } from "./properties_field.js";

export class CalendarPropertiesField extends CardPropertiesField {
    static template = "web.CalendarPropertiesField";
}

const calendarPropertiesField = {
    ...propertiesField,
    component: CalendarPropertiesField,
};

registerField({ name: "properties", view: "calendar" }, calendarPropertiesField);
