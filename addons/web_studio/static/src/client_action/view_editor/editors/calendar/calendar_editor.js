/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { useDebugMode } from "@web/core/debug/debug_context";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { omit } from "@web/core/utils/collections/objects";
import { calendarView, SCALE_LABELS } from "@web/views/calendar";
import { NewViewDialog } from "@web_studio/client_action/editor/new_view_dialogs/new_view_dialog";
import {
    fieldsToChoices,
    getStudioNoFetchFields,
} from "@web_studio/client_action/view_editor/editors/utils";
import { InteractiveEditorSidebar } from "@web_studio/client_action/view_editor/interactive_editor/interactive_editor_sidebar";
import { SidebarViewToolbox } from "@web_studio/client_action/view_editor/interactive_editor/sidebar_view_toolbox/sidebar_view_toolbox";
import { Property } from "@web_studio/client_action/view_editor/property/property";
import { useEditNodeAttributes } from "@web_studio/client_action/view_editor/view_editor_model";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";

export class CalendarEditorSidebar extends Component {
    static template = "web_studio.ViewEditor.CalendarEditorSidebar";
    static props = {
        openViewInForm: t.function().optional(),
        openDefaultValues: t.function().optional(),
    };
    static components = {
        InteractiveEditorSidebar,
        Property,
        SidebarViewToolbox,
    };
    props = useProps(this.constructor.props);

    setup() {
        this.debug = useDebugMode();
        this.viewEditorModel = proxy(useCurrentViewEditorModel());
        this.editArchAttributes = useEditNodeAttributes({ isRoot: true });
    }

    get archInfo() {
        return this.viewEditorModel.controllerProps.archInfo;
    }

    onViewAttributeChanged(value, name) {
        return this.editArchAttributes({ [name]: value });
    }

    get quickCreateFields() {
        return fieldsToChoices(
            this.viewEditorModel.fields,
            ["char"],
            (field) => field.store,
        );
    }

    get startDateFields() {
        return fieldsToChoices(this.viewEditorModel.fields, ["date", "datetime"]);
    }

    get delayFields() {
        return fieldsToChoices(this.viewEditorModel.fields, ["float", "integer"]);
    }

    get colorFields() {
        return fieldsToChoices(this.viewEditorModel.fields, [
            "many2one",
            "selection",
            "integer",
        ]);
    }

    get allDayFields() {
        return fieldsToChoices(this.viewEditorModel.fields, ["boolean"]);
    }

    get modeChoices() {
        return this.viewEditorModel.controllerProps.archInfo.scales.map((value) => ({
            value,
            label: SCALE_LABELS[value],
        }));
    }
}

class CalendarEditorArchParser extends calendarView.ArchParser {
    parse(...args) {
        const parsed = super.parse(...args);
        const { fieldNames } = getStudioNoFetchFields(null, args[0]);
        const toRemove = Object.fromEntries(fieldNames.map((fname) => [fname, true]));
        parsed.fieldNames = parsed.fieldNames.filter((fname) => !(fname in toRemove));
        parsed.filtersInfo = omit(parsed.filtersInfo, ...fieldNames);
        parsed.popoverFieldNodes = omit(parsed.popoverFieldNodes, ...fieldNames);
        return parsed;
    }
}

registry.category("studio_editors").add("calendar", {
    label: _t("Calendar"),
    icon: "fa-solid fa-calendar-days",
    group: "timeline",
    newViewDialog: NewViewDialog,
    ...calendarView,
    ArchParser: CalendarEditorArchParser,
    Sidebar: CalendarEditorSidebar,
});
