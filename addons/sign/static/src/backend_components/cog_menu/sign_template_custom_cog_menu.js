/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { Dropdown } from "@web/components/dropdown";
import { useService } from "@web/core/utils/hooks";
import { CogMenuItem } from "@web/search/cog_menu/cog_menu_item";

import { SignTemplateAccessRights } from "../sign_template/sign_template_access_rights.js";

export class SignTemplateCustomCogMenu extends Component {
    static template = "sign.SignTemplateCustomCogMenu";
    static components = { CogMenuItem, Dropdown };
    static props = {
        signTemplate: t.object(),
        hasSignRequests: t.boolean(),
        manageTemplateAccess: t.boolean(),
        onTemplateSaveClick: t.function(),
        documentId: t.number(),
        onEditTemplate: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.ui = useService("ui");
        this.action = useService("action");
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.dialogService = useService("dialog");
        this.state = proxy({
            properties: false,
        });
    }

    onTemplatePropertiesClick() {
        this.action.doAction({
            name: "Edit Template Form",
            type: "ir.actions.act_window",
            res_model: "sign.template",
            res_id: this.props.signTemplate.id,
            views: [[false, "form"]],
        });
    }

    get showEditButton() {
        return this.props.hasSignRequests;
    }

    onAccessRightsClick() {
        this.dialogService.add(SignTemplateAccessRights, {
            signTemplate: this.props.signTemplate,
            hasSignRequests: this.props.hasSignRequests,
        });
    }

    onPreviewClick() {
        this.action.doActionButton({
            type: "object",
            resModel: "sign.template",
            name: "action_template_preview",
            resIds: [this.props.signTemplate.id],
            args: JSON.stringify([this.props.documentId]),
        });
    }
}
