/** @odoo-module native */
import { t } from "@odoo/owl";
import { formatFloatFactor } from "@web/core/formatters";
import { registry } from "@web/core/registry";
import { elementRef } from "@web/core/utils/element_ref";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

import { getGridCellFactor, GridCell } from "./grid_cell.js";

function formatter(value, options = {}) {
    return formatFloatFactor(value, options);
}

export class FloatToggleGridCell extends GridCell {
    static props = { ...GridCell.props, factor: t.number().optional() };
    static template = "web_grid.FloatToggleGridCell";

    _setupEditor() {
        this.buttonRef = elementRef();
        useLayoutEffect(
            (buttonEl) => {
                if (buttonEl) {
                    buttonEl.focus();
                }
            },
            () => [this.buttonRef.el],
        );
    }

    get factor() {
        return getGridCellFactor(this.props);
    }

    get range() {
        return this.props.fieldInfo.options?.range || [0.0, 0.5, 1.0];
    }

    get value() {
        return super.value * this.factor;
    }

    get formattedValue() {
        return formatter(super.value, {
            digits: this.props.fieldInfo.digits || 2,
            factor: this.factor,
        });
    }

    onChange() {
        let currentIndex = this.range.indexOf(this.value);
        currentIndex++;
        if (currentIndex > this.range.length - 1) {
            currentIndex = 0;
        }
        this.update(this.range[currentIndex] / this.factor);
    }

    onCellClick(ev) {
        if (
            this.isEditable() &&
            !this.state.edit &&
            !ev.target.closest(".o_grid_search_btn")
        ) {
            this.onChange();
            this.props.onEdit(true);
        }
    }

    onKeyDown(ev) {
        this.props.onKeyDown(ev, this.state.cell);
    }
}

export const floatToggleGridCell = {
    component: FloatToggleGridCell,
    formatter,
};

registry.category("grid_components").add("float_toggle", floatToggleGridCell);
