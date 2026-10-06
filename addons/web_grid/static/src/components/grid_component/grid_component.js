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

    /**
     * The component rendering this field.
     *
     * `grid_components` keys two different kinds of component the same way:
     * the cell widgets a measure is edited with, and the row widgets a groupby
     * is labelled with. `integer` and `float` are registered as the first kind
     * and are also field types, so a row field of either type resolved to a
     * measure cell and died on props a row is never given -- "Invalid props
     * for component 'GridCell': 'getCell' is missing", from a view whose arch
     * says nothing about a cell.
     *
     * A row therefore takes a registry entry only if that entry can render a
     * row, and falls back to `GridRow` rather than to a component that wants a
     * bound cell.
     */
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
     * Whether a component expects to be bound to a grid cell. Asked of the
     * props it declares rather than of its ancestry: the row components are
     * not all `GridRow` subclasses (timesheet_grid's employee avatar row
     * extends `Component` directly), while every cell widget declares
     * `standardGridCellProps`, of which `getCell` is the part no row has.
     *
     * @param {typeof import("@odoo/owl").Component} component
     * @return {boolean}
     */
    static wantsBoundCell(component) {
        const { props } = component;
        return Boolean(props) && !Array.isArray(props) && "getCell" in props;
    }

    get gridComponentProps() {
        // A component may declare `props` as an object or as an array of
        // names; `key in [...]` asks an array for an index and would quietly
        // drop every prop.
        const { props } = this.gridComponent;
        const declared = new Set(Array.isArray(props) ? props : Object.keys(props));
        const gridComponentProps = Object.fromEntries(
            Object.entries(this.props).filter(([key]) => declared.has(key)),
        );
        gridComponentProps.classNames = `o_grid_component o_grid_component_${this.props.type} ${gridComponentProps.classNames || ""}`;
        return gridComponentProps;
    }
}
