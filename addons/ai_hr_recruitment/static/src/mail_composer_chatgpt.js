/** @odoo-module native */
import { MailComposerChatGPT, mailComposerChatGPT } from "@ai/mail_composer_chatgpt";
import { registry } from "@web/core/registry";

export class RefuseApplicantMailComposerChatGPT extends MailComposerChatGPT {
    get originalRecordModel() {
        return "hr.applicant";
    }

    get originalRecordId() {
        const record = this.props.record;
        return (
            record.data.applicant_ids?.records[0]?.resId ||
            (record.context.active_model === this.originalRecordModel
                ? record.context.active_id
                : false)
        );
    }
}

export const refuseApplicantMailComposerChatGPT = {
    ...mailComposerChatGPT,
    component: RefuseApplicantMailComposerChatGPT,
};

registry
    .category("fields")
    .add("refuse_applicant_mail_composer_chatgpt", refuseApplicantMailComposerChatGPT);
