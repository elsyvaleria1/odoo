/** @odoo-module native */

import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { FormController, formView } from "@web/views/form";

export class TeamFormController extends FormController {
    async beforeExecuteActionButton(clickParams) {
        if (clickParams.name !== "team_activate_multi_membership") {
            return super.beforeExecuteActionButton(...arguments);
        }
        const record = this.model.root;
        const teamId =
            this.props.resModel === "team.team"
                ? record.resId
                : record.data.team_id?.id;
        const flags = Object.fromEntries(
            Object.entries(record.data).filter(([name]) => name.startsWith("use_")),
        );
        try {
            await this.orm.call(
                "team.team",
                "action_activate_multi_membership",
                [teamId ? [teamId] : []],
                { flags },
            );
        } catch (error) {
            this.notification.add(
                error.data?.message ||
                    error.message ||
                    _t("An error occurred while activating the Multi-Team option."),
                { type: "danger" },
            );
            return false;
        }
        if (record.isNew || (await record.isDirty())) {
            const changes = { member_warning: false };
            if ("is_membership_multi" in record.fields) {
                changes.is_membership_multi = true;
            }
            await record.update(changes);
        } else {
            await record.load();
        }
        return false;
    }
}

registry.category("views").add("team_form", {
    ...formView,
    Controller: TeamFormController,
});
