/** @odoo-module native */
import { KanbanMany2OneAvatarEmployeeField } from "@hr/views/fields/many2one_avatar_employee_field/kanban_many2one_avatar_employee_field";
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { formatFloatTime } from "@web/core/formatters";
import {
    deserializeDateTime,
    endOf,
    formatValue,
    now,
    serializeDateTime,
    startOf,
    toLocaleString,
} from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useRecordObserver } from "@web/fields/hooks/record_observer";
import { standardWidgetProps } from "@web/views/widgets";

export class LeaveStatsComponent extends Component {
    static template = "hr_holidays.LeaveStatsComponent";
    static components = {
        KanbanMany2OneAvatarEmployeeField,
    };
    static props = { ...standardWidgetProps };
    props = useProps(this.constructor.props);

    setup() {
        this.orm = useService("orm");

        this.state = proxy({
            leaves: [],
            departmentLeaves: [],
            date: null,
            department: null,
            employee: null,
            type: null,
            has_parent_department: null,
            department_name: null,
        });
        this.date_format = { year: "numeric", month: "2-digit", day: "2-digit" };
        this.hour_format = { hour: "2-digit", minute: "2-digit" };
        this.state.date_from = this.props.record.data.date_from || now();
        this.state.date_to = this.props.record.data.date_to || now();
        this.state.employee = this.props.record.data.employee_id;
        this.state.department = this.props.record.data.department_id;

        onWillStart(async () => {
            await this.loadLeaves(this.state.employee);
            await this.loadDepartmentLeaves(this.state.department, this.state.employee);
        });

        this.loadGeneration = 0;
        useRecordObserver(async (record) => {
            const generation = ++this.loadGeneration;
            const dateFrom = record.data.date_from || now();
            const dateTo = record.data.date_to || now();
            const dateChanged =
                !this.state.date_from.equals(dateFrom) ||
                !this.state.date_to.equals(dateTo);
            this.state.date_from = dateFrom;
            this.state.date_to = dateTo;
            const employee = record.data.employee_id;
            const department = record.data.department_id;
            const proms = [];
            if (
                dateChanged ||
                (employee &&
                    (this.state.employee && this.state.employee.id) !== employee.id)
            ) {
                proms.push(this.loadLeaves(employee, generation));
            }
            if (
                dateChanged ||
                (department &&
                    (this.state.department && this.state.department.id) !==
                        department.id)
            ) {
                proms.push(this.loadDepartmentLeaves(department, employee, generation));
            }
            await Promise.all(proms);
            if (generation !== this.loadGeneration) {
                return;
            }
            this.state.date_from = dateFrom;
            this.state.employee = employee;
            this.state.department = department;
            if (this.state.department) {
                const department_name_array =
                    this.state.department.display_name.split("/");
                this.state.department_name = department_name_array.pop();
                this.state.has_parent_department = department_name_array.length > 0;
            }
        });
    }

    get thisYear() {
        return formatValue(this.state.date_from, "yyyy");
    }

    async loadDepartmentLeaves(department, employee, generation) {
        if (!(department && employee)) {
            if (generation === undefined || generation === this.loadGeneration) {
                this.state.departmentLeaves = [];
            }
            return;
        }

        const dateFrom = serializeDateTime(this.state.date_from);
        const dateTo = serializeDateTime(this.state.date_to);
        const leaves = await this.orm.webSearchRead(
            "hr.leave",
            [
                ["department_id", "=", department.id],
                ["state", "=", "validate"],
                ["employee_id", "!=", employee.id],
                ["date_from", "<=", dateTo],
                ["date_to", ">=", dateFrom],
            ],
            {
                specification: {
                    employee_id: { fields: { display_name: {} } },
                    date_from: {},
                    date_to: {},
                    number_of_days: {},
                    number_of_hours: {},
                    leave_type_request_unit: {},
                },
            },
        );
        if (generation === undefined || generation === this.loadGeneration) {
            this.state.departmentLeaves = this.arrangeData(leaves.records);
        }
    }

    async loadLeaves(employee, generation) {
        if (!employee) {
            if (generation === undefined || generation === this.loadGeneration) {
                this.state.leaves = [];
            }
            return;
        }

        const dateFrom = serializeDateTime(startOf(this.state.date_from, "year"));
        const dateTo = serializeDateTime(endOf(this.state.date_from, "year"));
        const leaves = await this.orm.webSearchRead(
            "hr.leave",
            [
                ["employee_id", "=", employee.id],
                ["state", "=", "validate"],
                ["date_from", "<=", dateTo],
                ["date_to", ">=", dateFrom],
            ],
            {
                specification: {
                    holiday_status_id: { fields: { display_name: {} } },
                    date_from: {},
                    date_to: {},
                    number_of_days: {},
                    number_of_hours: {},
                    leave_type_request_unit: {},
                },
            },
        );
        if (generation === undefined || generation === this.loadGeneration) {
            this.state.leaves = this.arrangeData(leaves.records);
        }
    }
    arrangeData(leaves) {
        leaves.forEach((leave) => {
            const date_from = deserializeDateTime(leave.date_from);
            const date_to = deserializeDateTime(leave.date_to);

            leave.date_from = toLocaleString(date_from, this.date_format);
            leave.hour_from = toLocaleString(date_from, this.hour_format);

            leave.date_to = toLocaleString(date_to, this.date_format);
            leave.hour_to = toLocaleString(date_to, this.hour_format);
            leave.number_of_hours = formatFloatTime(
                Number(leave.number_of_hours.toFixed(2)),
            );
            leave.number_of_days = Number(leave.number_of_days.toFixed(2));
        });
        return leaves;
    }
}

export const leaveStatsComponent = {
    component: LeaveStatsComponent,
    fieldDependencies: [
        { name: "employee_id", type: "many2one" },
        { name: "date_from", type: "datetime" },
        { name: "date_to", type: "datetime" },
        { name: "department_id", type: "many2one" },
    ],
};
registry.category("view_widgets").add("hr_leave_stats", leaveStatsComponent);
