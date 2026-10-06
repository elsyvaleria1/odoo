/** @odoo-module native */
import { Component, markup, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { useSearchModel } from "@web/search/search_model";

export class DocumentsActionHelper extends Component {
    static template = "document.DocumentsActionHelper";
    // folderId: the folder shown, so that going from one empty folder to
    // another renders the help of the new one
    static props = { noContentHelp: t.any(), folderId: t.any() };
    props = useProps(this.constructor.props);

    setup() {
        this.searchModel = useSearchModel();
    }

    get selectedFolderId() {
        return this.props.folderId;
    }

    /**
     * @returns {markup}
     */
    get noContentHelp() {
        if (typeof this.selectedFolderId === "number") {
            return this.props.noContentHelp;
        }
        const helpMessage = (() => {
            switch (this.selectedFolderId) {
                case "TRASH":
                    return _t("Documents moved to trash will show up here");
                case "RECENT":
                    return _t("Recently accessed Documents will show up here");
                case "SHARED":
                    return _t("Documents shared with you will appear here");
                case "MY":
                    return _t("Your personal space");
                default:
                    return _t("Select a folder to upload a document");
            }
        })();
        return markup`<p class="o_view_nocontent_smiling_face">${helpMessage}</p>`;
    }

    /** The alias of the folder shown, when the view shows that folder alone. */
    get mailTo() {
        if (typeof this.selectedFolderId !== "number") {
            return undefined;
        }
        const folderLeaves = this.searchModel.domain.filter(
            (leaf) => Array.isArray(leaf) && leaf.includes("folder_id"),
        );
        if (folderLeaves.length !== 1) {
            return undefined;
        }
        const folder = this.searchModel.getFolderById(this.selectedFolderId);
        if (!folder || folder.user_permission === "none") {
            return undefined;
        }
        return folder.alias_email || undefined;
    }
}
