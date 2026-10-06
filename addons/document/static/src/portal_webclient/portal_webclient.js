/** @odoo-module native */
import { Component, onMounted, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { MainComponentsContainer } from "@web/ui/main_components_container";
import { ActionContainer } from "@web/webclient/actions";

export class PortalWebclientWebClient extends Component {
    static props = {};
    static components = { ActionContainer, MainComponentsContainer };
    static template = "document.PortalWebclientWebClient";
    props = useProps(this.constructor.props);

    setup() {
        this.action = useService("action");
        this.documentService = useService("document.document");
        const initData = this.documentService.initData;
        onMounted(async () => {
            const action = await this.action.loadAction(
                "document.document_action_portal",
            );
            action.path = "documents";
            this.action.doAction(action, {
                additionalContext: initData.userFolderId
                    ? { searchpanel_default_user_folder_id: initData.userFolderId }
                    : {},
                stackPosition: "replaceCurrentAction",
            });
        });
    }
}
