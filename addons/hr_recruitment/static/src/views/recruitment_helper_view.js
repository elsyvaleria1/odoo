/** @odoo-module native */
import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";

export class RecruitmentActionHelper extends Component {
    static template = "hr_recruitment.RecruitmentActionHelper";
    static props = { noContentHelp: t.any() };
    props = useProps(this.constructor.props);
    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.state = proxy({
            hasDemoData: false,
        });
        onWillStart(async () => {
            const [hasDemoData, isRecruitmentUser] = await Promise.all([
                this.orm.call("hr.job", "is_recruitment_scenario_loaded", []),
                user.hasGroup("hr_recruitment.group_hr_recruitment_user"),
            ]);
            this.state.hasDemoData = hasDemoData;
            this.isRecruitmentUser = isRecruitmentUser;
        });
    }

    loadRecruitmentScenario() {
        this.actionService.doAction("hr_recruitment.action_load_demo_data");
    }

    actionCreateJobPosition() {
        this.actionService.doAction("hr.action_create_job_position");
    }
}
