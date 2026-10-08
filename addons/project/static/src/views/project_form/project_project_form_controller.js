/** @odoo-module native */
import { onWillStart, t } from "@odoo/owl";
import { useFocusTitle } from "@project/utils/project_utils";
import { user } from "@web/core/user";
import { FormControllerWithHTMLExpander } from "@web/views/form_with_html_expander/form_controller_with_html_expander";

import { ProjectTemplateDropdown } from "../components/project_template_dropdown.js";
import { ProjectManagerActionsMixin } from "../project_manager_actions_mixin.js";

export class ProjectProjectFormController extends ProjectManagerActionsMixin(
    FormControllerWithHTMLExpander,
) {
    static template = "project.ProjectFormView";
    static components = {
        ...FormControllerWithHTMLExpander.components,
        ProjectTemplateDropdown,
    };
    static props = {
        ...FormControllerWithHTMLExpander.props,
        focusTitle: t.boolean().optional(false),
    };

    setup() {
        super.setup();
        onWillStart(async () => {
            const featureGroups = await this.orm
                .cache()
                .call(this.props.resModel, "get_features_groups");
            const featureNames = Object.keys(featureGroups);
            const enabled = await Promise.all(
                featureNames.map((fName) => user.hasGroup(featureGroups[fName])),
            );
            this.featuresToObserve = Object.fromEntries(
                featureNames.map((fName, index) => [fName, enabled[index]]),
            );
        });

        if (this.props.focusTitle) {
            useFocusTitle(this.rootRef);
        }
    }

    /** @override */
    async onRecordSaved(record, changes) {
        await super.onRecordSaved(...arguments);
        const updatedFields = Object.keys(this.featuresToObserve).filter(
            (fName) => fName in changes,
        );
        if (updatedFields.length) {
            const updatedFeatures = await record.model.orm.call(
                record.resModel,
                "get_features_enabled",
                [updatedFields],
            );
            if (
                Object.entries(updatedFeatures).some(
                    ([fName, value]) => value !== this.featuresToObserve[fName],
                )
            ) {
                this.actionService.doAction("reload_context");
            }
        }
    }
}
