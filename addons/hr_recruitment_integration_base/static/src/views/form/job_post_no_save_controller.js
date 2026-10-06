/** @odoo-module native */
import { useDialogContext } from "@web/core/dialog_context_hooks";
import { useService } from "@web/core/utils/hooks";
import { FormController } from "@web/views/form";
import { prepareStaticActionMenuItems } from "@web/views/view_utils";

export class JobPostNoSaveFormController extends FormController {
    static template = "hr_recruitment_integration_base.job_post_no_save_form_template";

    setup() {
        super.setup();
        this.dialogContext = useDialogContext();
        this.action = useService("action");
        this.orm = useService("orm");
    }

    /**
     * @override
     */
    getStaticActionMenuItems() {
        const { activeActions } = this.archInfo;
        return prepareStaticActionMenuItems({
            duplicate: {
                isAvailable: () => activeActions.edit,
                callback: () => this.duplicateRecord(),
            },
            delete: {
                isAvailable: () => activeActions.delete && !this.model.root.isNew,
                callback: () => this.deleteRecord(),
                skipSave: true,
            },
        });
    }

    /**
     * @override
     */
    async duplicateRecord() {
        const action = await this.orm.call("hr.job.post", "action_post_job", [
            this.model.root.resId,
        ]);
        this.action.doAction(action);
    }
}
