/** @odoo-module native */
import { DocumentsControllerMixin } from "@document/views/document_controller_mixin";
import { ActivityController } from "@mail/views/web/activity/activity_controller";
import { _t } from "@web/core/translation";

export class DocumentsActivityController extends DocumentsControllerMixin(
    ActivityController,
) {
    static template = "document.DocumentsActivityController";
    static hasSelectionActions = false;

    get rendererProps() {
        const props = super.rendererProps;
        props.previewStore = this.documentStates.previewStore;
        return props;
    }

    /**
     * @override
     */
    async openRecord(record) {
        for (const selected of this.model.root.selection) {
            selected.selected = false;
        }
        record.selected = true;
        this.model.notify();
    }

    /**
     * @returns {Boolean}
     */
    isRecordPreviewable(record) {
        return this.model.activityData.activity_res_ids.includes(record.resId);
    }

    /**
     * @override
     * @param {number} templateID
     * @param {number} activityTypeID
     * @param {number[]} [resIds]
     */
    async sendMailTemplate(templateID, activityTypeID, resIds) {
        const sent = await super.sendMailTemplate(templateID, activityTypeID, resIds);
        if (sent) {
            this.notification.add(_t("Reminder emails have been sent."), {
                type: "success",
            });
        }
        return sent;
    }
}
