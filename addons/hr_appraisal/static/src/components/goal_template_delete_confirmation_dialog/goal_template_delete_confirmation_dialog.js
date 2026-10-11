/** @odoo-module native */
import { t } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { ConfirmationDialog, deleteConfirmationMessage } from "@web/ui/dialog";

export class GoalTemplateDeleteConfirmationDialog extends ConfirmationDialog {
    static template = "hr_appraisal.GoalTemplateDeleteConfirmationDialog";

    static props = {
        ...ConfirmationDialog.props,
        hasChildren: t.boolean(),
        confirmAllLabel: t.string().optional(_t("Delete with children")),
        confirmAll: t.function(),
        title: ConfirmationDialog.props.title.optional(_t("Bye-bye, record!")),
        body: ConfirmationDialog.props.body.optional(deleteConfirmationMessage),
        confirmLabel: ConfirmationDialog.props.confirmLabel.optional(_t("Delete")),
        cancel: ConfirmationDialog.props.cancel.optional(() => () => {}),
        cancelLabel: ConfirmationDialog.props.cancelLabel.optional(_t("No, keep it")),
    };
}
