/** @odoo-module native */
import {
    Component,
    onWillStart,
    onWillUpdateProps,
    proxy,
    t,
    useProps,
} from "@odoo/owl";
import { Notebook } from "@web/components/notebook";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useBus } from "@web/core/utils/hooks";
import { useRender } from "@web/core/utils/render_hooks";
import { useActiveElement } from "@web/ui/ui_service";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";

const tabsDisplay = {
    new: {
        class: "o_web_studio_new px-2",
        title: _t("Add"),
    },
    view: {
        class: "o_web_studio_view px-2",
        title: _t("View"),
    },
    properties: {
        class: "o_web_studio_properties px-2",
        title: _t("Properties"),
    },
};

export class InteractiveEditorSidebar extends Component {
    static components = { Notebook };
    static template = "web_studio.ViewEditor.InteractiveEditorSidebar";
    static props = { slots: t.object() };
    props = useProps(this.constructor.props);
    render = useRender();

    setup() {
        this.viewEditorModel = useCurrentViewEditorModel();
        this.editorModel = proxy(useCurrentViewEditorModel());
        this.tabsDisplay = tabsDisplay;
        useBus(this.editorModel.bus, "error", () => this.render(true));
        this.rootRef = elementRef();
        useActiveElement(this.rootRef);

        this._defaultTab = this.computeDefaultTab(this.props);
        this.editorModel.sidebarTab = this._defaultTab;

        onWillStart(() => {
            this.editorModel.resetSidebar();
        });
        onWillUpdateProps(() => {
            // This component takes slots: it is always re-rendered
            const editorModel = this.editorModel;
            if (editorModel.sidebarTab === "properties" && !editorModel.activeNode) {
                editorModel.resetSidebar();
            }
        });
    }

    get icons() {
        return {
            new: "fa-plus",
            view: "fa-television",
            properties: "fa-server",
        };
    }

    computeDefaultTab(props) {
        const slots = props.slots;
        const defaults = Object.keys(slots).filter((s) => slots[s].isDefault);
        if (defaults.length) {
            return defaults[0];
        }
        return "new" in slots ? "new" : "view";
    }

    get defaultTab() {
        return this.editorModel.sidebarTab || this._defaultTab;
    }

    onTabClicked(tab) {
        if (tab === "properties" && !this.editorModel.activeNodeXpath) {
            // a late page update of a render that showed a node since
            // deselected: the properties page has nothing to show
            return;
        }
        if (tab !== "properties") {
            this.editorModel.resetSidebar(tab);
        }
        this.editorModel.sidebarTab = tab;
    }
}
