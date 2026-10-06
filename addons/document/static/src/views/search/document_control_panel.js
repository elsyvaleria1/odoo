/** @odoo-module native */
import { DocumentsBreadcrumbs } from "@document/components/document_breadcrumbs";
import { DocumentsAction } from "@document/views/action/document_action";
import { DocumentsCogMenu } from "@document/views/cog_menu/document_cog_menu";
import { showsSelectionActions } from "@document/views/document_controller_mixin";
import { proxy } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useService } from "@web/core/utils/hooks";
import { useViewConfig } from "@web/core/view_config_hooks";
import { useViewModel } from "@web/model/model";
import { ControlPanel } from "@web/search/control_panel/control_panel";
import { useSearchModel } from "@web/search/search_model";

const log = makeLogger("document.control_panel");

export class DocumentsControlPanel extends ControlPanel {
    static template = "document.ControlPanel";
    static components = {
        ...ControlPanel.components,
        DocumentsBreadcrumbs,
        DocumentsCogMenu,
        DocumentsAction,
    };

    setup() {
        super.setup();
        this.config = useViewConfig();
        this.searchModel = useSearchModel();
        this.model = useViewModel();
        this.documentService = useService("document.document");

        this.rightPanelState = proxy(this.documentService.rightPanelReactive);
    }

    get currentFolderId() {
        return this.searchModel.getSelectedFolderId();
    }

    get showActions() {
        return (
            this.config.viewType !== "activity" &&
            showsSelectionActions(this.rightPanelState, this.model.root.selection)
        );
    }

    get pathBreadcrumbs() {
        log.logic("pathBreadcrumbs", () => ({
            folderId: this.searchModel.getSelectedFolderId(),
            activeModel: this.model.config.context.active_model || false,
            path: this.searchModel.getSelectedFolderAndParents().map((f) => f.id),
        }));
        if (this.model.config.context.active_model) {
            return [
                ...this.config.breadcrumbs.slice(0, -1),
                {
                    name: this.searchModel.getSelectedFolder().display_name,
                },
            ];
        }

        return this.searchModel
            .getSelectedFolderAndParents()
            .reverse()
            .map((folder) => ({
                jsId: folder.id,
                name: folder.display_name,
                onSelected: () => {
                    const folderSection = this.searchModel.getSections()[0];
                    this.searchModel.toggleCategoryValue(folderSection.id, folder.id);
                },
            }));
    }
}
