/** @odoo-module native */
import { Component, proxy, status, useProps } from "@odoo/owl";
import { Dropdown, DropdownItem } from "@web/components/dropdown";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { COG_GROUP } from "@web/search/cog_menu/cog_menu_group";
import { useSearchModel } from "@web/search/search_model";

import { isDocumentsCogMenuItemVisible } from "./document_cog_menu_item.js";

const log = makeLogger("document.cog_menu");

export class DocumentCogMenuPinAction extends Component {
    static template = "document.DocumentCogMenuPinAction";
    static components = { Dropdown, DropdownItem };
    static props = {};

    static isVisible = isDocumentsCogMenuItemVisible;
    props = useProps(this.constructor.props);

    setup() {
        this.searchModel = useSearchModel();
        this.documentService = useService("document.document");
        this.notification = useService("notification");

        this.documentsState = proxy({ actions: [], isLoading: true });
        this._reloadSearchModel = useDebounced(
            () => this.searchModel._reloadSearchModel(true),
            1500,
            { execBeforeUnmount: true },
        );

        const folderId = this.searchModel.getSelectedFolderId();
        this.documentService.getActions(folderId).then(
            (actions) => {
                if (status(this) !== "destroyed") {
                    this.documentsState.actions = actions;
                    this.documentsState.isLoading = false;
                }
            },
            (error) => {
                log.logic("getActions failed", () => ({
                    folderId,
                    error: String(error),
                }));
                if (status(this) !== "destroyed") {
                    this.documentsState.isLoading = false;
                    this._notifyError(error);
                }
            },
        );
    }

    _notifyError(error) {
        this.notification.add(error.data?.message || error.message || String(error), {
            type: "danger",
        });
    }

    async onEnableAction(actionId) {
        const currentFolderId = this.searchModel.getSelectedFolderId();
        const action = this.documentsState.actions.find((a) => a.id === actionId);
        if (!action) {
            return;
        }
        action.is_embedded = !action.is_embedded;
        try {
            await this.documentService.enableAction(currentFolderId, actionId);
        } catch (error) {
            action.is_embedded = !action.is_embedded;
            log.logic("enableAction failed", () => ({
                actionId,
                error: String(error),
            }));
            this._notifyError(error);
            return;
        }
        log.logic("action pinned", () => ({ actionId, pinned: action.is_embedded }));
        this._reloadSearchModel();
    }
}

export const documentCogMenuPinAction = {
    Component: DocumentCogMenuPinAction,
    groupNumber: COG_GROUP.APP,
    isDisplayed: (env) =>
        DocumentCogMenuPinAction.isVisible(
            env,
            ({ folder, documentService }) =>
                documentService.userIsDocumentUser &&
                documentService.isEditable(folder),
        ),
};
