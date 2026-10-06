/** @odoo-module native */
import { registry } from "@web/core/registry";
import { X2ManyField, x2ManyField } from "@web/fields/relational/x2many";

import { EmissionFactorListRenderer } from "./emission_factor_list_renderer.js";

export class EmissionFactorX2ManyField extends X2ManyField {
    static components = {
        ...X2ManyField.components,
        ListRenderer: EmissionFactorListRenderer,
    };
}

registry.category("fields").add("emission_factor_x2many", {
    ...x2ManyField,
    component: EmissionFactorX2ManyField,
});
