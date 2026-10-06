/** @odoo-module native */
import { formatFloatTime } from "@web/core/formatters";
import { parseFloatTime } from "@web/core/parsers";
import { registry } from "@web/core/registry";

import { GridCell } from "./grid_cell.js";

function formatter(value, options = {}) {
    return formatFloatTime(value, { ...options, noLeadingZeroHour: true });
}

export class FloatTimeGridCell extends GridCell {
    get formattedValue() {
        return formatter(this.value);
    }

    get inputMode() {
        return "text";
    }

    parse(value) {
        return parseFloatTime(value);
    }
}

export const floatTimeGridCell = {
    component: FloatTimeGridCell,
    formatter,
};

registry.category("grid_components").add("float_time", floatTimeGridCell);
