/** @odoo-module native */
import { registry } from "@web/core/registry";
import {
    SelectionField,
    selectionField,
} from "@web/fields/selection/selection/selection_field";

export class CarrierTypeSelection extends SelectionField {
    get options() {
        const carrierTypes = this.props.record.context.carrier_types;
        if (carrierTypes) {
            return Object.keys(carrierTypes).map((carrier) => [carrier, carrier]);
        } else {
            return [];
        }
    }

    onChange(value) {
        this.props.record.update(
            { [this.props.name]: value },
            { save: this.props.autosave },
        );
    }
}

export const carrierTypeSelection = {
    ...selectionField,
    supportedTypes: ["char"],
    component: CarrierTypeSelection,
};

registry.category("fields").add("carrier_type_selection", carrierTypeSelection);
