/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";

import { GridCell } from "../grid_cell.js";
import { GridRow } from "../grid_row/grid_row.js";

const gridComponentRegistry = registry.category("grid_components");

export class GridComponent extends Component {
    static props = null;
    static template = "web_grid.GridComponent";
    props = useProps(this.constructor.props);

    get gridComponent() {
        if (this.props.component) {
            return this.props.component;
        }
        const entry = gridComponentRegistry.contains(this.props.type)
            ? gridComponentRegistry.get(this.props.type)
            : null;
        if (this.props.isMeasure) {
            if (entry) {
                return entry.component;
            }
            console.warn(`Missing widget: ${this.props.type} for grid component`);
            return GridCell;
        }
        if (entry && !GridComponent.wantsBoundCell(entry.component)) {
            return entry.component;
        }
        return GridRow;
    }

    /**
     * @param {typeof import("@odoo/owl").Component} component
     * @return {boolean}
     */
    static wantsBoundCell(component) {
        const { props } = component;
        return Boolean(props) && !Array.isArray(props) && "getCell" in props;
    }

    get gridComponentProps() {
        const { props } = this.gridComponent;
        const declared = new Set(Array.isArray(props) ? props : Object.keys(props));
        const gridComponentProps = Object.fromEntries(
            Object.entries(this.props).filter(([key]) => declared.has(key)),
        );
        gridComponentProps.classNames = `o_grid_component o_grid_component_${this.props.type} ${gridComponentProps.classNames || ""}`;
        return gridComponentProps;
    }
}
