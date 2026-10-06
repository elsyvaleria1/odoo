/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { useDebugMode } from "@web/core/debug/debug_context";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";

export class SidebarViewToolbox extends Component {
    static template = "web_studio.ViewEditor.ViewToolbox";
    static props = {
        canEditXml: t.boolean().optional(),
        onMore: t.function().optional(),
        openDefaultValues: t.function().optional(),
        canEditDefaultValues: t.boolean().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.viewEditorModel = useCurrentViewEditorModel();
        this.debug = useDebugMode();
    }
}
