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
            // read_group answers a grouping that has a label with a
            // `(value, label)` pair -- a date granularity's, here. A
            // many2one's pair is left whole for Many2OneGridRow, which
            // needs the id to link to the record.
            value = value[1];
        }
        return value;
    }

    /**
     * Whether the group this row stands for has a value at all, as distinct
     * from having a falsy one. `0` is a group like any other -- a grid grouped
     * by an integer has one whenever a record carries no sequence -- and
     * labelling it "None" states something else entirely. Odoo answers an
     * unset value with `false`, and a selection whose key is gone resolves to
     * `undefined`.
     *
     * @return {boolean}
     */
    get hasValue() {
        const { value } = this;
        return value !== undefined && value !== null && value !== false && value !== "";
    }
}

export const gridRow = {
    component: GridRow,
};

registry.category("grid_components").add("selection", gridRow).add("char", gridRow);
