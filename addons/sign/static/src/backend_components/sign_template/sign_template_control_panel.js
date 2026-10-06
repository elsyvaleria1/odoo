/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { multiFileUpload } from "@sign/backend_components/multi_file_upload";
import { SignStatusIndicator } from "@sign/backend_components/sign_status_indicator/sign_status_indicator";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { ControlPanel } from "@web/search/control_panel/control_panel";

import { SignTemplateCustomCogMenu } from "../cog_menu/sign_template_custom_cog_menu.js";
import { SignTemplateHeaderTags } from "./sign_template_header_tags.js";

export class SignTemplateControlPanel extends Component {
    static template = "sign.SignTemplateControlPanel";
    static components = {
        ControlPanel,
        SignStatusIndicator,
        SignTemplateCustomCogMenu,
        SignTemplateHeaderTags,
    };
    static props = {
        responsibleCount: t.number(),
        hasSignRequests: t.boolean(),
        actionType: t.string(),
        signTemplate: t.object(),
        goBackToKanban: t.function(),
        signStatus: t.object(),
        manageTemplateAccess: t.boolean(),
        onTemplateSaveClick: t.function(),
        hasSignersWithoutItems: t.boolean(),
        documentId: t.number(),
        onEditTemplate: t.function(),
        referenceDoc: t.string().optional(),
        activityId: t.number().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.controlPanelDisplay = {};
        this.nextTemplate = multiFileUpload.getNext() ?? false;
        this.action = useService("action");
        this.orm = useService("orm");
    }

    get customCogMenuProps() {
        return {
            signTemplate: this.props.signTemplate,
            hasSignRequests: this.props.hasSignRequests,
            manageTemplateAccess: this.props.manageTemplateAccess,
            onTemplateSaveClick: this.props.onTemplateSaveClick,
            documentId: this.props.documentId,
            onEditTemplate: this.props.onEditTemplate,
        };
    }

    get templateHeaderTagsProps() {
        return {
            signTemplate: this.props.signTemplate,
            hasSignRequests: this.props.hasSignRequests,
        };
    }

    get showShareButton() {
        return (
            this.props.actionType !== "sign_send_request" &&
            this.props.responsibleCount <= 1
        );
    }

    async onSendClick() {
        await this.saveBeforeAction();
        return this.action.doActionButton({
            type: "object",
            resModel: "sign.template",
            name: "open_sign_send_dialog",
            resIds: [this.props.signTemplate.id],
            context: {
                sign_directly_without_mail: false,
                show_email: true,
                has_signers_without_items: this.props.hasSignersWithoutItems,
                default_reference_doc: this.props.referenceDoc,
                default_activity_id: this.props.activityId,
                default_model: "sign.template",
                default_res_ids: [this.props.signTemplate.id],
            },
        });
    }

    async saveBeforeAction() {
        if (this.props.signStatus.isTemplateChanged) {
            await this.props.signStatus.save();
        }
    }

    async onSignNowClick() {
        await this.saveBeforeAction();
        return this.action.doActionButton({
            type: "object",
            resModel: "sign.template",
            name: "open_sign_send_dialog",
            resIds: [this.props.signTemplate.id],
            context: {
                sign_directly_without_mail: true,
                has_signers_without_items: this.props.hasSignersWithoutItems,
                default_reference_doc: this.props.referenceDoc,
                default_activity_id: this.props.activityId,
            },
        });
    }

    async onShareClick() {
        await this.saveBeforeAction();
        const action = await this.orm.call(
            "sign.template",
            "open_shared_sign_request",
            [this.props.signTemplate.id],
        );
        this.action.doAction(action);
    }

    async onNextDocumentClick() {
        await this.saveBeforeAction();
        const templateName = this.nextTemplate.name;
        const templateId = parseInt(this.nextTemplate.template);
        multiFileUpload.removeFile(templateId);
        this.action.doAction({
            type: "ir.actions.client",
            tag: "sign.Template",
            name: _t("Template %s", templateName),
            params: {
                sign_edit_call: "sign_template_edit",
                id: templateId,
                sign_directly_without_mail: false,
            },
        });
    }
}
