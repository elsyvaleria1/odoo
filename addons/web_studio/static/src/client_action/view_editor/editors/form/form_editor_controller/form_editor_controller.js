/** @odoo-module native */
import { onMounted, onPatched, proxy, t } from "@odoo/owl";
import { useRender } from "@web/core/utils/render_hooks";
import { useViewConfig } from "@web/core/view_config_hooks";
import { formView } from "@web/views/form";
import { useModelConfigFetchInvisible } from "@web_studio/client_action/view_editor/editors/utils";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";

function useExternalParentInModel(model, parentRecord) {
    model._createRoot = (config, data) =>
        new model.constructor.Record(model, config, data, { parentRecord });
}

export class FormEditorController extends formView.Controller {
    static props = {
        ...formView.Controller.props,
        parentRecord: t.or([t.object(), t.literal(null)]).optional(),
    };

    setup() {
        super.setup();
        this.config = useViewConfig();
        useModelConfigFetchInvisible(this.model);
        this.mailTemplate = null;
        this.hasFileViewerInArch = false;

        this.viewEditorModel = proxy(useCurrentViewEditorModel());
        const render = useRender();

        if (this.props.parentRecord) {
            useExternalParentInModel(this.model, this.props.parentRecord);
        }

        onMounted(() => {
            const xpath = this.viewEditorModel.lastActiveNodeXpath;
            if (xpath && xpath.includes("notebook")) {
                const tabXpath = xpath.match(/.*\/page\[\d+\]/)[0];
                const tab = document.querySelector(
                    `[data-studio-xpath='${tabXpath}'] a`,
                );
                if (tab) {
                    this.notebookElementData = {
                        xpath,
                        restore: Boolean(this.viewEditorModel.activeNodeXpath),
                        sidebarTab: this.viewEditorModel.sidebarTab,
                        isTab: xpath.length === tabXpath.length,
                    };
                    tab.click();
                    render();
                }
            } else {
                this.notebookElementData = null;
            }
        });

        onPatched(() => {
            if (this.notebookElementData) {
                if (
                    this.notebookElementData.isTab &&
                    this.viewEditorModel.lastActiveNodeXpath !==
                        this.notebookElementData.xpath
                ) {
                    return;
                }
                if (this.notebookElementData.restore) {
                    this.config.onNodeClicked(this.notebookElementData.xpath);
                } else {
                    this.viewEditorModel.resetSidebar(
                        this.notebookElementData.sidebarTab,
                    );
                }
                this.notebookElementData = null;
            }
        });
    }

    beforeUnload() {}

    _shouldUseSubEnv() {
        return false;
    }
}
