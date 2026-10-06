/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { AutoComplete } from "@web/components/autocomplete";
import { rpc } from "@web/core/network";

export class Many2One extends Component {
    static template = "hr_attendance.Many2One";
    static components = { AutoComplete };
    static props = { token: t.string(), update: t.function(), value: t.string() };
    props = useProps(this.constructor.props);

    get sources() {
        return [
            {
                options: this.loadOptionsSource.bind(this),
                optionSlot: "option",
            },
        ];
    }

    async loadOptionsSource(input) {
        const employeeName = input;
        const data = await rpc("/hr_attendance/get_employees_without_badge", {
            token: this.props.token,
            name: employeeName,
        });
        if (data?.status === "success") {
            return data.employees.map((emp) => ({
                data: { id: emp.id },
                label: emp.name,
                onSelect: () => this.props.update({ id: emp.id, name: emp.name }),
            }));
        }
        return [];
    }
}
