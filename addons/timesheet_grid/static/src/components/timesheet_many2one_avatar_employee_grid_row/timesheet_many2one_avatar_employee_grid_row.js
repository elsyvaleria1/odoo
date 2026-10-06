/** @odoo-module native */
import { AvatarCardEmployeePopover } from "@hr/components/avatar_card_employee/avatar_card_employee_popover";
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { usePopover } from "@web/ui/popover";
import {
    Many2OneGridRow,
    many2OneGridRow,
} from "@web_grid/components/many2one_grid_row/many2one_grid_row";

import { useTimesheetOvertimeProps } from "../../hooks/useTimesheetOvertimeProps.js";
import { EmployeeOvertimeIndication } from "../employee_overtime_indication/employee_overtime_indication.js";
import { TimesheetGridMany2OneGridRow } from "../timesheet_grid_many2one/timesheet_grid_many2one_field.js";

export class TimesheetMany2OneAvatarEmployeeGridRow extends Component {
    static template = "timesheet_grid.TimesheetMany2OneAvatarEmployeeGridRow";

    static components = {
        Many2OneGridRow,
        EmployeeOvertimeIndication,
    };

    static props = { ...TimesheetGridMany2OneGridRow.props };
    props = useProps(this.constructor.props);

    setup() {
        super.setup(...arguments);
        this.ui = useService("ui");
        this.employeeOvertimeProps = useTimesheetOvertimeProps(this);
        this.avatarCard = usePopover(AvatarCardEmployeePopover);
    }

    get relation() {
        return (
            this.props.relation || this.props.model.fieldsInfo[this.props.name].relation
        );
    }

    get many2OneProps() {
        return Object.fromEntries(
            Object.entries(this.props).filter(
                ([key]) =>
                    key !== "classNames" &&
                    key in this.constructor.components.Many2OneGridRow.props,
            ),
        );
    }

    get resId() {
        return this.value && this.value[0];
    }

    get displayName() {
        return this.value ? this.value[1] : "";
    }

    get value() {
        return this.props.value !== undefined
            ? this.props.value
            : this.props.row.initialRecordValues[this.props.name];
    }

    get timesheetOvertimeProps() {
        const { units_to_work, uom, worked_hours } = this.employeeOvertimeProps.props;
        return {
            allocated_hours: units_to_work,
            uom,
            worked_hours,
        };
    }

    openCard(ev) {
        if (this.ui.isSmall) {
            return;
        }
        const target = ev.currentTarget;
        if (!this.avatarCard.isOpen) {
            this.avatarCard.open(target, {
                id: this.resId,
            });
        }
    }
}

export const timesheetMany2OneAvatarEmployeeGridRow = {
    ...many2OneGridRow,
    component: TimesheetMany2OneAvatarEmployeeGridRow,
};

registry
    .category("grid_components")
    .add("timesheet_many2one_avatar_employee", timesheetMany2OneAvatarEmployeeGridRow);
