/** @odoo-module native */
import { TimesheetUOM } from "@hr_timesheet/components/timesheet_uom/timesheet_uom";
import { registry } from "@web/core/registry";
import { FloatFactorGridCell } from "@web_grid/components/float_factor_grid_cell";
import { FloatTimeGridCell } from "@web_grid/components/float_time_grid_cell";
import { FloatToggleGridCell } from "@web_grid/components/float_toggle_grid_cell";
import { GridCell, standardGridCellProps } from "@web_grid/components/grid_cell";

export class GridTimesheetUOM extends TimesheetUOM {
    static props = {
        ...standardGridCellProps,
        readonly: standardGridCellProps.readonly.optional(true),
        editMode: standardGridCellProps.editMode.optional(false),
    };

    static components = {
        GridCell,
        FloatFactorGridCell,
        FloatToggleGridCell,
        FloatTimeGridCell,
    };

    get timesheetComponent() {
        return registry
            .category("grid_components")
            .get(this.timesheetUOMService.timesheetWidget, {
                component: GridCell,
                formatter: this.timesheetUOMService.formatter,
            }).component;
    }
}
