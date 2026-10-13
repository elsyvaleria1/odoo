/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { COG_GROUP, isActWindowView } from "@web/search/cog_menu/cog_menu_group";
import { CogMenuItem } from "@web/search/cog_menu/cog_menu_item";

const cogMenuRegistry = registry.category("cogMenu");
/** @extends Component */
export class DocumentImportCogMenu extends Component {
    static template = "sign.import.documents.DocumentImportCogMenu";
    static components = { CogMenuItem };
    static props = {};
    props = useProps(this.constructor.props);

    setup() {
        this.action = useService("action");
    }

    openDocumentImportWizard() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "wizard.sign.template.import.document",
            view_mode: "form",
            views: [[false, "form"]],
            target: "new",
            name: _t("Import from Documents"),
        });
    }
}

cogMenuRegistry.add(
    "document-import-cog-menu",
    {
        Component: DocumentImportCogMenu,
        groupNumber: COG_GROUP.DATA,
        isDisplayed: async (env) =>
            !env.isSmall &&
            ["sign.request", "sign.template"].includes(env.searchModel.resModel) &&
            isActWindowView(env) &&
            env.config.viewType !== "form" &&
            (await user.hasGroup("document.group_documents_user")),
    },
    { sequence: 30 },
);
