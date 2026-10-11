/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { formatFloatTime } from "@web/core/formatters";
import { formatFloat } from "@web/core/utils/format/numbers";

export class EmployeeOvertimeIndication extends Component {
    static props = {
        allocated_hours: t.number().optional(),
        uom: t.string().optional("hours"),
        worked_hours: t.number().optional(),
    };
    static template = "timesheet_grid.EmployeeOvertimeIndication";
    props = useProps(this.constructor.props);

    get shouldShowHours() {
        return this.props.allocated_hours > 0;
    }

    get colorClasses() {
        if (!this.shouldShowHours) {
            return "";
        }
        return this.props.worked_hours < this.props.allocated_hours
            ? "text-danger"
            : "text-success";
    }

    get overtime() {
        return this.props.worked_hours - this.props.allocated_hours;
    }

    get overtimeIndication() {
        if (!this.shouldShowHours) {
            return null;
        }
        if (this.overtime === 0) {
            return null;
        }
        let overtimeIndication = this.overtime > 0 ? "+" : "";
        if (this.props.uom === "days") {
            overtimeIndication += formatFloat(this.overtime);
        } else {
            overtimeIndication += formatFloatTime(this.overtime);
        }
        return overtimeIndication;
    }
}
