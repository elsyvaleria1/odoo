/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { gridView } from "@web_grid/views/grid_view";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";
import {
    InteractiveEditorSidebar,
    Property,
    SidebarViewToolbox,
    useEditNodeAttributes,
} from "@web_studio/editor";

export class GridEditorSidebar extends Component {
    static template = "web_grid_studio.GridEditorSidebar";
    static props = {
        openViewInForm: t.function().optional(),
        openDefaultValues: t.function().optional(),
    };
    static components = { InteractiveEditorSidebar, Property, SidebarViewToolbox };
    props = useProps(this.constructor.props);

    setup() {
        this.viewEditorModel = proxy(useCurrentViewEditorModel());
        this.editArchAttributes = useEditNodeAttributes({ isRoot: true });
    }

    get archInfo() {
        return this.viewEditorModel.controllerProps.archInfo;
    }

    // The root booleans grid_view.rng admits. Row, column and measure fields
    // are `<field>` children with a `type`, edited as nodes.
    get toggles() {
        return [
            {
                name: "hide_line_total",
                key: "hideLineTotal",
                label: _t("Hide Line Total"),
            },
            {
                name: "hide_column_total",
                key: "hideColumnTotal",
                label: _t("Hide Column Total"),
            },
            {
                name: "barchart_total",
                key: "hasBarChartTotal",
                label: _t("Bar Chart Total"),
            },
            { name: "create_inline", key: "createInline", label: _t("Create Inline") },
            { name: "display_empty", key: "displayEmpty", label: _t("Display Empty") },
        ];
    }

    onViewAttributeChanged(value, name) {
        return this.editArchAttributes({ [name]: value ? "1" : "0" });
    }
}

registry.category("studio_editors").add("grid", {
    ...gridView,
    label: _t("Grid"),
    icon: "fa-solid fa-th",
    group: "multiple",
    Sidebar: GridEditorSidebar,
});
