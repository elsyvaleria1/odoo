/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { localization } from "@web/core/l10n/localization";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useStudioEditorContext } from "@web_studio/client_action/editor/studio_editor_context";
import { useStudioServiceAsReactive } from "@web_studio/studio_service";
const editorTabRegistry = registry.category("web_studio.editor_tabs");

class Breadcrumbs extends Component {
    static template = "web_studio.EditorMenu.Breadcrumbs";
    static props = { currentTab: t.object(), switchTab: t.function() };
    props = useProps(this.constructor.props);
    setup() {
        this.studioContext = useStudioEditorContext();
        this.editionFlow = proxy(this.studioContext.editionFlow);
    }
    get breadcrumbs() {
        const currentTab = this.props.currentTab;
        const crumbs = [
            {
                data: {
                    name: currentTab.name,
                },
                handler: () => this.props.switchTab({ tab: currentTab.id }),
            },
            ...this.editionFlow.breadcrumbs,
        ];
        return crumbs.map((crumb, index) => ({ ...crumb, id: index + 1 }));
    }
}

export class EditorMenu extends Component {
    static props = { switchTab: t.function(), switchView: t.function() };
    static template = "web_studio.EditorMenu";

    static components = { Breadcrumbs };
    props = useProps(this.constructor.props);
    setup() {
        this.studioContext = useStudioEditorContext();
        this.l10n = localization;
        this.studio = useStudioServiceAsReactive();
        this.editionFlow = proxy(this.studioContext.editionFlow);
    }

    get activeViews() {
        const action = this.studio.editedAction;
        const viewTypes = (action._views || action.views).map(([, type]) => type);
        return registry
            .category("studio_editors")
            .getEntries()
            .filter(([type]) => viewTypes.includes(type))
            .map(([type, editor]) => ({
                type,
                title: editor.label,
                iconClasses: editor.icon,
            }));
    }

    get editorTabs() {
        const entries = editorTabRegistry.getEntries();
        return entries.map((entry) => Object.assign({}, entry[1], { id: entry[0] }));
    }

    get currentTab() {
        return this.editorTabs.find((tab) => tab.id === this.studio.editorTab);
    }

    openTab(tab) {
        this.props.switchTab({ tab });
    }
}

editorTabRegistry
    .add(
        "views",
        { name: _t("Views"), action: "web_studio.action_editor" },
        { sequence: 10 },
    )
    .add("automations", { name: _t("Automations") }, { sequence: 20 })
    .add("actions_server", { name: _t("Actions") }, { sequence: 30 })
    .add("automation_webhooks", { name: _t("Webhooks") }, { sequence: 40 })
    .add("acl", { name: _t("Access Control") }, { sequence: 50 })
    .add("filters", { name: _t("Filter Rules") }, { sequence: 60 });
