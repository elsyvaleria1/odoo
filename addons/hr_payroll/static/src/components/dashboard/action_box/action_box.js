/** @odoo-module native */
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";

export class PayrollDashboardActionBox extends Component {
    static template = "hr_payroll.ActionBox";
    static props = null;
    props = useProps(this.constructor.props);

    setup() {
        this.actionService = useService("action");
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = proxy({
            loading: true,
            warnings: {},
        });
        onWillStart(() => {
            this.orm
                .call("hr.payslip", "get_dashboard_warnings")
                .then((data) => {
                    this.state.warnings = data;
                })
                .catch(() => {
                    this.notification.add(_t("Could not load the payroll warnings."), {
                        type: "danger",
                    });
                })
                .finally(() => {
                    this.state.loading = false;
                });
            return Promise.resolve(true);
        });
    }
}
