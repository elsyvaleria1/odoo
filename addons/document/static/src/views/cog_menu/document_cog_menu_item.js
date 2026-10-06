/** @odoo-module native */
import { documentActions, documentActionText } from "@document/views/document_actions";
import { useDocumentContext } from "@document/views/document_context";
import { reloadDocumentsView } from "@document/views/hooks";
import { Component, useProps } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useService } from "@web/core/utils/hooks";
import { useViewScope } from "@web/model/view_scope";
import { CogMenuItem } from "@web/search/cog_menu/cog_menu_item";
import { useSearchModel } from "@web/search/search_model";

const log = makeLogger("document.cog_menu");

/**
 * @param {Object} env
 * @param {Function|false} [isVisibleAdditional]
 * @returns {boolean}
 */
export function isDocumentsCogMenuItemVisible(
    { config, searchModel, services },
    isVisibleAdditional = false,
) {
    if (
        !(
            config &&
            searchModel &&
            searchModel.resModel === "document.document" &&
            services
        )
    ) {
        return false;
    }
    // a picker in a dialog shows folders to pick from, not to act on
    if (searchModel.context.documents_view_secondary) {
        return false;
    }
    const folder = searchModel.getSelectedFolder();
    const documentService = services["document.document"];
    const visible = Boolean(
        folder &&
        documentService &&
        ["kanban", "list"].includes(config.viewType) &&
        (!isVisibleAdditional ||
            isVisibleAdditional({ folder, config, searchModel, documentService })),
    );
    log.logic("itemVisible", () => ({
        folderId: folder?.id,
        viewType: config.viewType,
        visible,
    }));
    return visible;
}

export class DocumentsCogMenuItem extends Component {
    static template = "document.DocumentCogMenuItem";
    static components = { CogMenuItem };
    static props = {};

    static isVisible = isDocumentsCogMenuItemVisible;
    props = useProps(this.constructor.props);

    setup() {
        this.viewScope = useViewScope();
        this.searchModel = useSearchModel();
        this.documentService = useService("document.document");
    }

    async onItemSelected() {
        const folder = this.searchModel?.getSelectedFolder();
        if (!folder) {
            return;
        }
        await this.doActionOnFolder(folder);
    }

    async reload() {
        await reloadDocumentsView(this.viewScope);
    }

    async doActionOnFolder() {}
}

/**
 * A cog menu entry acting on the current folder through one of
 * `documentActions`.
 *
 * @param {string} actionId a key of `documentActions`
 * @param {number} groupNumber
 */
export function makeDocumentsCogMenuItem(actionId, groupNumber) {
    const action = documentActions[actionId];
    class DocumentsCogMenuActionItem extends DocumentsCogMenuItem {
        setup() {
            super.setup();
            this.documentContext = useDocumentContext();
            const folder = this.searchModel.getSelectedFolder();
            this.icon = documentActionText(action, "icon", folder);
            this.label = documentActionText(action, "label", folder);
        }

        doActionOnFolder(folder) {
            return action.run(
                {
                    documentService: this.documentService,
                    model: this.viewScope.model,
                    reload: () => this.reload(),
                    bus: this.documentContext.documentsView.bus,
                },
                folder,
            );
        }
    }
    return {
        Component: DocumentsCogMenuActionItem,
        groupNumber,
        isDisplayed: (env) =>
            DocumentsCogMenuItem.isVisible(env, ({ folder, documentService }) =>
                action.isVisible(documentService, folder),
            ),
    };
}
