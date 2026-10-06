/** @odoo-module native */
import { Component, markRaw, onWillUpdateProps, proxy, t, useProps } from "@odoo/owl";
import { useSetupAction } from "@web/core/action_hook";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useBus, useService } from "@web/core/utils/hooks";
import { useRender } from "@web/core/utils/render_hooks";
import { provideViewConfig } from "@web/core/view_config_hooks";
import { getDefaultConfig } from "@web/views/view";
import { standardActionServiceProps } from "@web/webclient/actions";
import { useStudioEditorContext } from "@web_studio/client_action/editor/studio_editor_context";
import { StudioView } from "@web_studio/client_action/view_editor/studio_view";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";
import { XmlResourceEditor } from "@web_studio/client_action/xml_resource_editor/xml_resource_editor";

import { InteractiveEditor } from "./interactive_editor/interactive_editor.js";
import { useViewEditorModel } from "./view_editor_hook.js";

class ViewXmlEditor extends XmlResourceEditor {
    static props = { ...XmlResourceEditor.props, studioViewArch: t.string() };
    render = useRender();
    setup() {
        super.setup();
        this.viewEditorModel = useCurrentViewEditorModel();
        useBus(this.viewEditorModel.bus, "error", () => this.render(true));
        this.studioViewState = proxy({ arch: this.props.studioViewArch });

        onWillUpdateProps((nextProps) => {
            if (nextProps.studioViewArch !== this.props.studioViewArch) {
                const studioResource = this.getStudioResource(
                    this.state.resourcesOptions,
                );
                if (studioResource) {
                    studioResource.value.arch = nextProps.studioViewArch;
                }
            }
        });
    }

    getStudioResource(resourcesOptions) {
        return resourcesOptions.find(
            (opt) => opt.value.id === this.viewEditorModel.studioViewId,
        );
    }
}

export class ViewEditor extends Component {
    static props = { ...standardActionServiceProps };
    static components = { StudioView, InteractiveEditor, ViewXmlEditor };
    static template = "web_studio.ViewEditor";

    static displayName = _t("View Editor");
    props = useProps(this.constructor.props);

    setup() {
        this.studioContext = useStudioEditorContext();
        /* Services */
        this.studio = useService("studio");
        this.orm = useService("orm");
        /* MISC */
        // Avoid pollution from the real actionService's env
        // Set config compatible with View.js
        provideViewConfig(getDefaultConfig());

        // Usefull for drag/drop
        this.rootRef = elementRef();
        this.rendererRef = elementRef();

        const initialState = {};
        const breadcrumbs = this.studioContext.editionFlow.breadcrumbs;
        if (breadcrumbs.length) {
            initialState.showInvisible = breadcrumbs[0].initialState.showInvisible;
            initialState.activeNodeXpath =
                breadcrumbs.at(-1).initialState.activeNodeXpath;
        }

        this.viewEditorModel = useViewEditorModel(this.rendererRef, { initialState });

        useSetupAction({
            getLocalState: () => {
                // Use this as a hook that is triggered when the actionService knows
                // this component will be unmounted, is still alive and the new action
                // is being built.
                // We store the state in the breadcrumbs, because there two ways
                // to respawn the editor:
                // - the editor's breadcrumbs
                // - the standard actionService breadcrumbs
                const breadcrumbs = this.viewEditorModel.breadcrumbs;
                breadcrumbs[0].initialState = markRaw({
                    showInvisible: this.viewEditorModel.showInvisible,
                });
                const last = breadcrumbs.at(-1);
                last.initialState = markRaw({
                    ...last.initialState,
                    activeNodeXpath: this.viewEditorModel.activeNodeXpath,
                });
            },
        });
    }

    get interactiveEditorKey() {
        const { viewType, breadcrumbs } = this.viewEditorModel;
        let key = viewType;
        if (breadcrumbs.length > 1) {
            key += `_${breadcrumbs.length}`;
        }
        return key;
    }

    onSaveXml({ resourceId, oldCode, newCode }) {
        this.viewEditorModel.doOperation({
            type: "replace_arch",
            viewId: resourceId,
            oldArch: oldCode,
            newArch: newCode,
        });
    }

    onXmlEditorClose() {
        this.viewEditorModel.switchMode();
    }
}
registry.category("actions").add("web_studio.view_editor", ViewEditor);
