/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { isMobileOS } from "@web/core/browser/feature_detection";
import { FileUploader } from "@web/core/file_upload";
import { useService } from "@web/core/utils/hooks";

export class CrmBusinessCardScanner extends Component {
    static template = "crm_enterprise.CrmBusinessCardScanner";
    static components = {
        FileUploader,
    };
    static props = {};
    props = useProps(this.constructor.props);

    setup() {
        this.ui = useService("ui");
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.businessCardsAttachmentsIds = [];
        this.isMobileOS = isMobileOS();
    }

    async onFileUploaded(file) {
        const attachmentData = {
            name: file.name,
            type: "binary",
            mimetype: file.type,
            datas: file.data,
        };
        this.ui.block();
        try {
            const [attachmentId] = await this.orm.create("ir.attachment", [
                attachmentData,
            ]);
            await this.orm.call("ir.attachment", "generate_access_token", [
                attachmentId,
            ]);
            this.businessCardsAttachmentsIds.push(attachmentId);
        } finally {
            this.ui.unblock();
        }
    }

    async onUploadComplete() {
        this.ui.block();
        try {
            const actionValues = await this.orm.call(
                "crm.lead",
                "action_ocr_business_cards",
                [[], this.businessCardsAttachmentsIds],
            );
            if (actionValues) {
                this.action.doAction(actionValues);
            }
        } finally {
            this.businessCardsAttachmentsIds = [];
            this.ui.unblock();
        }
    }
}
