/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

import { useOpenPayRun } from "../../../views/payslip_run_hook.js";

export class PayrollDashboardPayslipBatch extends Component {
    static template = "hr_payroll.PayslipBatch";
    static props = { batches: t.any() };
    props = useProps(this.constructor.props);

    setup() {
        this.actionService = useService("action");
        this.openPayRun = useOpenPayRun();
    }

    onClickTitle() {
        this.actionService.doAction("hr_payroll.action_hr_payslip_run");
    }

    getColorFromState(stateCode) {
        const colorMap = {
            "01_ready": "text-bg-info",
            "02_close": "text-bg-success",
            "03_paid": "text-bg-primary",
            "04_cancel": "text-bg-warning",
        };
        return colorMap[stateCode] || "text-bg-info";
    }

    /** @param {number} batchID */
    onClickLine(batchID) {
        this.openPayRun({
            id: batchID,
        });
    }
}
