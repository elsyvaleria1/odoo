/** @odoo-module native */
import { EsgGraphDashboard } from "@esg/components/esg_dashboard/esg_graph_dashboard/esg_graph_dashboard";
import { Component, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";

export class EsgHrSexParityBox extends Component {
    static template = "esg_hr.SexParityBox";
    static components = { EsgGraphDashboard };
    static props = { data: t.object() };
    props = useProps(this.constructor.props);

    setup() {
        this.actionService = useService("action");
    }

    openEmployeeReportLeadershipViews() {
        this.actionService.doAction("esg_hr.action_esg_employee_report_sex_parity");
    }

    get overallPayGapPercentage() {
        if (this.props.data.overall_pay_gap === false) {
            return _t("N/A");
        }
        return _t("%(overall_pay_gap)s%", {
            overall_pay_gap: this.props.data.overall_pay_gap,
        });
    }
}
