/** @odoo-module native */
import { DocumentsBreadcrumbs } from "@document/components/document_breadcrumbs";
import { DocumentsAction } from "@document/views/action/document_action";
import { showsSelectionActions } from "@document/views/document_controller_mixin";
import { onPatched, proxy } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { useViewConfig } from "@web/core/view_config_hooks";
import { useViewModel } from "@web/model/model";
import { ControlPanel } from "@web/search/control_panel/control_panel";
import { useSearchModel } from "@web/search/search_model";

export class DocumentsControlPanel extends ControlPanel {
    static template = "document.ControlPanel";
    static components = {
        ...ControlPanel.components,
        DocumentsBreadcrumbs,
        DocumentsAction,
    };

    setup() {
        super.setup();
        this.config = useViewConfig();
        this.searchModel = useSearchModel();
        this.model = useViewModel();
        this.ui = useService("ui");
        this.documentService = useService("document.document");

        this.rightPanelState = proxy(this.documentService.rightPanelReactive);

        onPatched(() => {
            // this view's panel: a picker dialog's view has its own
            const searchPanelContainer = this.root.el
                ?.closest(".o_view_controller")
                ?.querySelector(".o_content > .o_search_panel");
            if (searchPanelContainer) {
                searchPanelContainer.classList.toggle(
                    "d-none",
                    this.ui.isSmall && this.model.root.selection.length,
                );
            }
        });
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
