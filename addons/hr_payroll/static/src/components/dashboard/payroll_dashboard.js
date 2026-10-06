/** @odoo-module native */
import { PayrollDashboardActionBox } from "@hr_payroll/components/dashboard/action_box/action_box";
import { PayrollDashboardStats } from "@hr_payroll/components/dashboard/payroll_stats/payroll_stats";
import { PayrollDashboardPayslipBatch } from "@hr_payroll/components/dashboard/payslip_batch/payslip_batch";
import { PayrollDashboardTodo } from "@hr_payroll/components/dashboard/todo_list/todo_list";
import { DashboardEmptyScreen } from "@hr_payroll/components/dashboard_empty_screen/dashboard_empty_screen";
import { Component, onWillStart, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions";

class PayrollDashboardComponent extends Component {
    static template = "hr_payroll.Dashboard";
    static components = {
        DashboardEmptyScreen,
        PayrollDashboardActionBox,
        PayrollDashboardPayslipBatch,
        PayrollDashboardTodo,
        PayrollDashboardStats,
    };
    static props = { ...standardActionServiceProps };
    props = useProps(this.constructor.props);

    setup() {
        this.orm = useService("orm");
        onWillStart(async () => {
            this.dashboardData = await this.orm.call(
                "hr.payslip",
                "get_payroll_dashboard_data",
                [],
            );
        });
    }
}

registry.category("actions").add("hr_payroll_dashboard", PayrollDashboardComponent);

export default PayrollDashboardComponent;
