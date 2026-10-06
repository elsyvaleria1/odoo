/** @odoo-module native */
import { GoalTemplateDeleteConfirmationDialog } from "@hr_appraisal/components/goal_template_delete_confirmation_dialog/goal_template_delete_confirmation_dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useViewConfig } from "@web/core/view_config_hooks";
import {
    addFieldDependencies,
    extractFieldsFromArchInfo,
} from "@web/model/relational_model";
import { FormController, formView } from "@web/views/form";

export class AppraisalGoalDeleteFormController extends FormController {
    setup() {
        super.setup(...arguments);
        this.config = useViewConfig();
        const { activeFields, fields } = extractFieldsFromArchInfo(
            this.archInfo,
            this.props.fields,
        );
        addFieldDependencies(activeFields, fields, [
            { name: "child_ids", type: "one2many" },
        ]);
        this.orm = useService("orm");
        this.action = useService("action");
        this.deleteRecordsWithConfirmation = () => this.deleteRecursiveRecord();
    }
    async deleteRecursiveRecord() {
        this.dialogService.add(GoalTemplateDeleteConfirmationDialog, {
            hasChildren: this.model.root.data.child_ids.count > 0,
            confirm: async () => {
                await this.model.root.delete();
                this.config.historyBack();
            },
            confirmAll: async () => {
                await this.orm.call(this.model.root.resModel, "recursive_unlink", [
                    this.model.root.resId,
                ]);
                this.config.historyBack();
            },
        });
    }
}

export const appraisalGoalDeleteFormView = {
    ...formView,
    Controller: AppraisalGoalDeleteFormController,
};

registry
    .category("views")
    .add("appraisal_goal_delete_form", appraisalGoalDeleteFormView);
