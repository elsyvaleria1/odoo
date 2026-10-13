/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";

export class GridRow extends Component {
    static template = "web_grid.GridRow";
    static props = {
        name: t.string(),
        model: t.object(),
        row: t.object(),
        classNames: t.string().optional(""),
        context: t.object().optional({}),
        style: t.string().optional(""),
        value: t.any().optional(),
    };
    props = useProps(this.constructor.props);

    get value() {
        let value =
            this.props.value !== undefined
                ? this.props.value
                : this.props.row.initialRecordValues[this.props.name];
        const fieldInfo = this.props.model.fieldsInfo[this.props.name];
        if (fieldInfo.type === "selection") {
            return fieldInfo.selection.find(([key]) => key === value)?.[1];
        }
        if (fieldInfo.type !== "many2one" && Array.isArray(value)) {
            value = value[1];
        }
        return value;
    }

    /** @return {boolean} */
    get hasValue() {
        const { value } = this;
        return value !== undefined && value !== null && value !== false && value !== "";
    }
}

export const gridRow = {
    component: GridRow,
};

registry.category("grid_components").add("selection", gridRow).add("char", gridRow);
