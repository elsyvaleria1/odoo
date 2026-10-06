/** @odoo-module native */

import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { COG_GROUP } from "@web/search/cog_menu/cog_menu_group";
import { CogMenuItem } from "@web/search/cog_menu/cog_menu_item";

const cogMenuRegistry = registry.category("cogMenu");

export class MultipleAppraisalsCogMenu extends Component {
    static template = "hr_appraisal.MultipleAppraisalsCogMenu";
    static components = { CogMenuItem };
    static props = {};
    props = useProps(this.constructor.props);

    setup() {
        this.action = useService("action");
    }

    async openAppraisalCampaignWizard() {
        return this.action.doAction(
            "hr_appraisal.action_view_appraisal_campaign_wizard",
        );
    }
}

export const multipleAppraisalsCogMenu = {
    Component: MultipleAppraisalsCogMenu,
    groupNumber: COG_GROUP.APP,
    isDisplayed: async ({ config, searchModel }) =>
        searchModel.resModel === "hr.appraisal" &&
        ["kanban", "list"].includes(config.viewType) &&
        (await user.hasGroup("hr_appraisal.group_hr_appraisal_user")),
};

cogMenuRegistry.add("multiple-appraisals-cog-menu", multipleAppraisalsCogMenu, {
    sequence: 11,
});
