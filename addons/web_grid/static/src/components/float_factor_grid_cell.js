/** @odoo-module native */
import { t } from "@odoo/owl";
import { formatFloatFactor } from "@web/core/formatters";
import { registry } from "@web/core/registry";

import { getGridCellFactor, GridCell } from "./grid_cell.js";

function formatter(value, options = {}) {
    return formatFloatFactor(value, options);
}

export class FloatFactorGridCell extends GridCell {
    static props = { ...GridCell.props, factor: t.number().optional() };

    parse(value) {
        return super.parse(value) / this.factor;
    }

    get factor() {
        return getGridCellFactor(this.props);
    }

    get value() {
        return super.value * this.factor;
    }

    get formattedValue() {
        return formatter(this.value);
    }
}

export const floatFactorGridCell = {
    component: FloatFactorGridCell,
    formatter,
};

registry.category("grid_components").add("float_factor", floatFactorGridCell);
