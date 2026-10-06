/** @odoo-module native */
import { Component, EventBus, onWillDestroy, proxy, useProps, xml } from "@odoo/owl";
import { useAppContext } from "@web/core/app_context";
import { registry } from "@web/core/registry";
import { omit } from "@web/core/utils/collections/objects";
import {
    provideEventBus,
    useBus,
    useEventBus,
    useService,
} from "@web/core/utils/hooks";
import {
    installActionCacheInvalidation,
    makeActionManager,
} from "@web/webclient/actions";
import { provideStudioEditorContext } from "@web_studio/client_action/editor/studio_editor_context";
import {
    provideHostedStudioEnv,
    useServicesOverrides,
} from "@web_studio/client_action/utils";
import { useStudioServiceAsReactive } from "@web_studio/studio_service";

import { AppMenuEditor } from "./app_menu_editor/app_menu_editor.js";
import { EditionFlow } from "./edition_flow.js";
import { EditorMenu } from "./editor_menu/editor_menu.js";
import { NewModelItem } from "./new_model_item/new_model_item.js";
import { StudioActionContainer } from "./studio_action_container.js";

class DialogWithEnv extends Component {
    static template = xml`<t t-component="this.props.Component" t-props="this.componentProps" />`;
    static props = null;
    props = useProps(this.constructor.props);

    setup() {
        provideHostedStudioEnv(this.props.env);
    }

    get componentProps() {
        const additionalProps = omit(this.props, "Component", "env", "componentProps");
        return { ...this.props.componentProps, ...additionalProps };
    }
}
const dialogService = {
    dependencies: ["dialog"],
    start(env, { dialog }) {
        function addDialog(Component, _props, options) {
            const props = { env, Component, componentProps: _props };
            return dialog.add(DialogWithEnv, props, options);
        }
        // `dialog` is a class instance (`DialogService`) since the
        // service-shape refactor: `closeAll`/`destroy` live on the prototype,
        // so a spread (`{ ...dialog, add }`) copies only own fields and
        // silently drops them — the action manager's
        // `dialog.closeAll({ noReload: true })` then crashes inside Studio's
        // sub-env. Derive from the instance instead: the wrapper shadows `add`
        // and delegates every other method (and the shared stack) to the real
        // service.
        return Object.assign(Object.create(dialog), { add: addDialog });
    },
};

const actionServiceStudio = {
    dependencies: ["studio", "dialog"],
    start(env, { studio }) {
        const router = {
            current: { hash: {} },
            pushState() {},
            stateToUrl() {},
            hideKeyFromUrl: () => {},
        };
        const action = makeActionManager(env, router);
        // ``makeActionManager`` no longer installs the RPC cache-invalidation
        // listener (the ctor used to, leaking a permanent rpcBus listener that
        // pinned every short-lived Studio manager forever). Install it
        // explicitly here and expose the disposer so the Editor component tears
        // it down in ``onWillDestroy`` — one listener per live editor, none
        // after it closes.
        action.uninstallActionCacheInvalidation =
            installActionCacheInvalidation(action);
        // ``ActionManager`` is an ES6 class since the native-ESM loader refactor;
        // ``doAction`` reads ``this.fetchAction``, so the method
        // reference must stay bound to its instance. ``Object.assign`` below
        // replaces ``action.doAction`` with the wrapper, hence the original is
        // captured (bound) here rather than called via ``action.doAction``.
        const _doAction = action.doAction.bind(action);

        async function doAction(actionRequest, options) {
            if (actionRequest === "web_studio.action_edit_report") {
                return studio.setParams({
                    editedReport: options.report,
                });
            }
            return _doAction(...arguments);
        }

        return Object.assign(action, { doAction });
    },
};

const menuButtonsRegistry = registry.category("studio_navbar_menubuttons");
export class Editor extends Component {
    static template = "web_studio.Editor";
    static props = {};
    static components = {
        EditorMenu,
        StudioActionContainer,
    };

    static menuButtonsId = 1;
    props = useProps(this.constructor.props);
    setup() {
        this.appContext = useAppContext();
        const globalBus = useEventBus();
        const newBus = new EventBus();
        useBus(globalBus, "CLEAR-UNCOMMITTED-CHANGES", (ev) =>
            newBus.trigger("CLEAR-UNCOMMITTED-CHANGES", ev.detail),
        );
        useBus(globalBus, "MENUS:APP-CHANGED", (ev) =>
            newBus.trigger("MENUS:APP-CHANGED", ev.detail),
        );

        provideEventBus(newBus);

        useServicesOverrides({
            dialog: dialogService,
            action: actionServiceStudio,
        });
        this.studio = useService("studio");

        const editionFlow = new EditionFlow(this.appContext, {
            dialog: useService("dialog"),
            studio: useStudioServiceAsReactive(),
            view: useService("view"),
        });
        provideStudioEditorContext({
            editionFlow,
        });

        this.actionService = useService("action");

        this.state = proxy({ actionContainerId: 1 });
        useBus(this.studio.bus, "UPDATE", async () => {
            this.state.actionContainerId++;
        });

        // Push instance-specific components in the navbar. Because we want those elements
        // immediately, we add them at setup time, not onMounted.
        // Also, because they are Editor instance-specific, and that Destroyed is mostly called
        // after the new instance is created, we need to remove the old entries before adding the new ones
        menuButtonsRegistry.getEntries().forEach(([name]) => {
            if (
                name.startsWith("app_menu_editor_") ||
                name.startsWith("new_model_item_")
            ) {
                menuButtonsRegistry.remove(name);
            }
        });
        const menuButtonsId = this.constructor.menuButtonsId++;
        menuButtonsRegistry.add(`app_menu_editor_${menuButtonsId}`, {
            Component: AppMenuEditor,
            props: { env: this.appContext },
        });
        menuButtonsRegistry.add(`new_model_item_${menuButtonsId}`, {
            Component: NewModelItem,
        });
        onWillDestroy(() => {
            menuButtonsRegistry.remove(`app_menu_editor_${menuButtonsId}`);
            menuButtonsRegistry.remove(`new_model_item_${menuButtonsId}`);
            // Dispose the Studio action manager's RPC cache-invalidation
            // listener installed in ``actionServiceStudio.start``. Without this
            // every Studio entry leaked a permanent rpcBus listener pinning the
            // dead manager, so each subsequent ir.actions write fanned out N+1
            // stale breadcrumb refreshes.
            this.actionService.uninstallActionCacheInvalidation?.();
        });
    }

    switchView({ viewType }) {
        this.studio.setParams({ viewType, editorTab: "views" });
    }
    switchViewLegacy(ev) {
        this.studio.setParams({ viewType: ev.detail.view_type });
    }

    switchTab({ tab }) {
        this.studio.setParams({ editorTab: tab });
    }
}
