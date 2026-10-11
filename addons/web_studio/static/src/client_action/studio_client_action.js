/** @odoo-module native */
import {
    Component,
    onMounted,
    onPatched,
    onWillStart,
    onWillUnmount,
    useProps,
} from "@odoo/owl";
import { registry } from "@web/core/registry";
import { user as originalUser } from "@web/core/user";
import { useBus, useEventBus, useService } from "@web/core/utils/hooks";
import { useRender } from "@web/core/utils/render_hooks";
import { session } from "@web/session";
import { standardActionServiceProps } from "@web/webclient/actions";
import {
    computeAppsAndMenuItems,
    isDefaultHomeMenuConfig,
    parseHomeMenuConfig,
    reorderApps,
} from "@web/webclient/menus/menu_utils";

import { AppCreator } from "./app_creator/app_creator.js";
import { Editor } from "./editor/editor.js";
import { StudioNavbar } from "./navbar/navbar.js";
import { StudioHomeMenu } from "./studio_home_menu/studio_home_menu.js";

export class StudioClientAction extends Component {
    static template = "web_studio.StudioClientAction";
    static target = "fullscreen";
    static props = { ...standardActionServiceProps };
    static components = {
        StudioNavbar,
        StudioHomeMenu,
        Editor,
        AppCreator,
    };
    props = useProps(this.constructor.props);
    render = useRender();

    setup() {
        this.bus = useEventBus();
        const ownConfig = parseHomeMenuConfig(originalUser.settings?.homemenu_config);
        const homemenuConfig = (
            isDefaultHomeMenuConfig(ownConfig)
                ? parseHomeMenuConfig(session.homemenu_default_config)
                : ownConfig
        ).order;
        this.studio = useService("studio");
        useBus(this.studio.bus, "UPDATE", () => {
            this.render();
        });

        this.menus = useService("menu");
        this.actionService = useService("action");
        let apps = computeAppsAndMenuItems(this.menus.getMenuAsTree("root")).apps;
        if (homemenuConfig.length) {
            reorderApps(apps, homemenuConfig);
        }
        this.homeMenuProps = {
            apps: apps,
        };
        useBus(this.bus, "MENUS:APP-CHANGED", () => {
            apps = computeAppsAndMenuItems(this.menus.getMenuAsTree("root")).apps;
            if (homemenuConfig.length) {
                reorderApps(apps, homemenuConfig);
            }
            this.homeMenuProps = {
                apps: apps,
            };
            this.render();
        });

        onWillStart(() => this.studio.ready);
        onMounted(() => {
            document.body.classList.add("o_in_studio");
            this.studio.pushState();
        });
        onPatched(() => this.studio.pushState());
        onWillUnmount(() => document.body.classList.remove("o_in_studio"));
    }

    async onNewAppCreated({ action_id, menu_id }) {
        await this.menus.reload();
        this.menus.setCurrentMenu(menu_id);
        const action = await this.actionService.loadAction(action_id);

        let initViewType = "form";
        if (!action.views.some((vTuple) => vTuple[1] === initViewType)) {
            initViewType = action.views[0][1];
        }
        this.studio.setParams({
            mode: this.studio.MODES.EDITOR,
            editorTab: "views",
            action,
            viewType: initViewType,
        });
    }
}

registry.category("lazy_components").add("StudioClientAction", StudioClientAction);
registry.category("actions").add("studio", StudioClientAction, { force: true });
