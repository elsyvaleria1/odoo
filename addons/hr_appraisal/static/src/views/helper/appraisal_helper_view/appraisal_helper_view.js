/** @odoo-module native */
import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";

export class AppraisalActionHelper extends Component {
    static template = "hr_appraisal.AppraisalActionHelper";
    static props = { noContentHelp: t.any() };
    props = useProps(this.constructor.props);
    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.state = proxy({
            hasDemoData: false,
        });
        onWillStart(async () => {
            this.hasAppraisalRight = await user.hasGroup(
                "hr_appraisal.group_hr_appraisal_user",
            );
            this.employeeNumber = await this.orm.searchCount("hr.employee", [
                ["company_id", "in", user.context.allowed_company_ids],
            ]);
            this.state.hasDemoData = await this.orm.call(
                "hr.appraisal",
                "has_demo_data",
                [],
            );
        });
    }

    loadAppraisalScenario() {
        this.actionService.doAction("hr_appraisal.action_load_appraisal_demo_data");
    }

    loadCreateAppraisal() {
        this.actionService.doAction({
            name: _t("Appraisals"),
            res_model: "hr.appraisal",
            type: "ir.actions.act_window",
            views: [[false, "form"]],
            view_mode: "form",
            target: "current",
        });
    }

    loadCreateEmployee() {
        this.actionService.doAction({
            name: _t("Employees"),
            res_model: "hr.employee",
            type: "ir.actions.act_window",
            views: [[false, "form"]],
            view_mode: "form",
            target: "current",
        });
    }

    loadAppraisalCampaignWizard() {
        this.actionService.doAction({
            name: _t("Appraisal Campaign"),
            res_model: "wizard.hr.appraisal.create",
            type: "ir.actions.act_window",
            views: [[false, "form"]],
            view_mode: "form",
            target: "new",
        });
    }
}
