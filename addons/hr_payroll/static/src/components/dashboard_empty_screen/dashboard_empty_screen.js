/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class DashboardEmptyScreen extends Component {
    static template = "hr_payroll.DashboardEmptyScreen";
    static props = {};
    props = useProps(this.constructor.props);

    setup() {
        this.ui = useService("ui");
        this.action = useService("action");
    }

    openEmployeeCreate() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "hr.employee",
            views: [[false, "form"]],
            target: "current",
        });
    }
}
