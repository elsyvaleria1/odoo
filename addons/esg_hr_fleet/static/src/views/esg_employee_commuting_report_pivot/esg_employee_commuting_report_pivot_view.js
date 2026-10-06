/** @odoo-module native */
import { registry } from "@web/core/registry";
import { pivotView } from "@web/views/pivot";

import { EsgEmployeeCommutingReportPivotRenderer } from "./esg_employee_commuting_report_pivot_renderer.js";

export const EsgEmployeeCommutingReportPivotView = {
    ...pivotView,
    Renderer: EsgEmployeeCommutingReportPivotRenderer,
    buttonTemplate: "esg_hr_fleet.EsgEmployeeCommutingReportPivotView.Buttons",
};

registry
    .category("views")
    .add("esg_employee_commuting_report_pivot", EsgEmployeeCommutingReportPivotView);
