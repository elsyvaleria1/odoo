/** @odoo-module native */
import { Component, onError, proxy, t, toRaw, useProps, xml } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { useViewConfig } from "@web/core/view_config_hooks";
import { kanbanView } from "@web/views/kanban";
import { FieldStudio } from "@web_studio/client_action/view_editor/editors/components/field_studio";
import { StudioHook } from "@web_studio/client_action/view_editor/editors/components/studio_hook_component";
import { ViewButtonStudio } from "@web_studio/client_action/view_editor/editors/components/view_button_studio";
import { WidgetStudio } from "@web_studio/client_action/view_editor/editors/components/widget_studio";
import { computeXpath } from "@web_studio/client_action/view_editor/editors/xml_utils";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";

import { KanbanEditorCompiler } from "./kanban_editor_compiler.js";

class FieldStudioKanbanRecord extends FieldStudio {
    isX2ManyEditable() {
        return false;
    }
}

const KanbanRecord = kanbanView.Renderer.components.KanbanRecord;

class KanbanEditorRecordMenu extends Component {
    static props = { slots: t.object(), studioXpath: t.string() };
    static template = "web_studio.KanbanEditorRecordMenu";
    props = useProps(this.constructor.props);
}

function useSafeKanban() {
    const state = proxy({ hasError: false });
    const viewEditorModel = toRaw(useCurrentViewEditorModel());
    onError((error) => {
        const hasError = state.hasError;
        if (hasError || viewEditorModel.isInEdition) {
            throw error;
        }
        state.hasError = true;
    });
    return state;
}

class SafeKanbanRecord extends KanbanRecord {
    static template = "web_studio.SafeKanbanRecord";
    setup() {
        super.setup();
        this.safe = useSafeKanban();
    }
    onGlobalClick() {}
}

class _KanbanEditorRecord extends KanbanRecord {
    static template = "web_studio.SafeKanbanRecord";
    static menuTemplate = "web_studio.SafeKanbanRecordMenu";
    static components = {
        ...KanbanRecord.components,
        Field: FieldStudioKanbanRecord,
        Widget: WidgetStudio,
        StudioHook,
        ViewButton: ViewButtonStudio,
        KanbanRecordMenu: KanbanEditorRecordMenu,
    };
    setup() {
        super.setup();
        this.config = useViewConfig();
        this.viewEditorModel = proxy(useCurrentViewEditorModel());
        this.dialogService = useService("dialog");
        this.safe = useSafeKanban();
    }
    onGlobalClick(ev) {
        const el = ev.target.closest(".o-web-studio-editor--element-clickable");
        if (el) {
            this.config.onNodeClicked(el.getAttribute("studioxpath"));
        }
    }
    isFieldValueEmpty(value) {
        if (value === null) {
            return true;
        }
        if (Array.isArray(value)) {
            return !value.length;
        }
        return !value;
    }
    get dropdownXpath() {
        const compiledTemplateMenu =
            this.props.archInfo.templateDocs[this.constructor.KANBAN_MENU_ATTRIBUTE];
        return computeXpath(compiledTemplateMenu, "kanban");
    }
}

export class KanbanEditorRecord extends Component {
    static props = { ...KanbanRecord.props };
    static template = xml`<t t-component="this.KanbanRecord" t-props="this.kanbanRecordProps" />`;
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.viewEditorModel = useCurrentViewEditorModel();
    }

    get KanbanRecord() {
        if (this.viewEditorModel.mode !== "interactive") {
            return SafeKanbanRecord;
        } else {
            return _KanbanEditorRecord;
        }
    }
    get kanbanRecordProps() {
        const props = { ...this.props };
        if (this.viewEditorModel.mode === "interactive") {
            props.Compiler = KanbanEditorCompiler;
        }
        return props;
    }
}
