/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { COG_GROUP, isActWindowView } from "@web/search/cog_menu/cog_menu_group";
import { CogMenuItem } from "@web/search/cog_menu/cog_menu_item";

const cogMenuRegistry = registry.category("cogMenu");

/**
 * 'Request signature' menu
 *
 * This component is used to request a signature and link it to a document.
 * @extends Component
 */
export class SignRequestCogMenu extends Component {
    static template = "sign.SignRequestCogMenu";
    static components = { CogMenuItem };
    static props = {};
    props = useProps(this.constructor.props);

    setup() {
        this.action = useService("action");
    }

    signRequest() {
        /*
         * Fetch resModel from the controller props as it is static until the view changes.
         * Fetch resId from the current state since the state is mutable with newly created records.
         */
        const resModel = this.action.currentController.props.resModel;
        const resId = this.action.currentController.currentState?.resId;
        const referenceDoc = resId && resModel ? `${resModel},${resId}` : false;
        if (referenceDoc) {
            this.action.doActionButton({
                type: "object",
                resModel: "sign.template",
                name: "open_sign_send_dialog",
                resIds: [],
                context: {
                    sign_directly_without_mail: false,
                    default_reference_doc: referenceDoc,
                    sign_from_record: true,
                    default_model: resModel,
                    default_res_ids: [resId],
                },
            });
        }
    }
}

export const SignRequestCogMenuItem = {
    Component: SignRequestCogMenu,
    groupNumber: COG_GROUP.APP,
    isDisplayed: (env) =>
        isActWindowView(env, ["form"]) &&
        !["discuss.channel", "sign.request"].includes(env.searchModel.resModel) &&
        Boolean(env.searchModel.searchViewFields?.["message_ids"]),
};

cogMenuRegistry.add("sign-request-menu", SignRequestCogMenuItem, { sequence: 10 });
