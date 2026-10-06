/** @odoo-module native */
import { registry, useRegistry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { NavBar } from "@web/webclient/navbar/navbar";
import {
    NotEditableActionError,
    useStudioServiceAsReactive,
} from "@web_studio/studio_service";

import { HomeMenuCustomizer } from "./home_menu_customizer/home_menu_customizer.js";

const menuButtonsRegistry = registry.category("studio_navbar_menubuttons");
export class StudioNavbar extends NavBar {
    static template = "web_studio.StudioNavbar";
    static components = {
        ...NavBar.components,
        HomeMenuCustomizer,
    };
    setup() {
        super.setup();
        this.ui = useService("ui");
        this.studio = useStudioServiceAsReactive();
        this.actionManager = useService("action");
        this.dialogManager = useService("dialog");
        this.notification = useService("notification");
        this.menuButtonEntries = useRegistry(menuButtonsRegistry);
    }
    onMenuToggle() {
        this.studio.toggleHomeMenu();
    }
    closeStudio() {
        this.studio.leave();
    }
    async onNavBarDropdownItemSelection(menu) {
        if (menu.actionID) {
            try {
                await this.studio.open(this.studio.MODES.EDITOR, menu.actionID);
            } catch (e) {
                if (e instanceof NotEditableActionError) {
                    const options = { type: "danger" };
                    this.notification.add(
                        _t("This action is not editable by Studio"),
                        options,
                    );
                    return;
                }
                throw e;
            }
        }
    }
    get hasBackgroundAction() {
        return (
            this.studio.editedAction ||
            this.studio.MODES.APP_CREATOR === this.studio.mode
        );
    }
    get isInApp() {
        return this.studio.mode === this.studio.MODES.EDITOR;
    }
    get menuButtons() {
        return Object.fromEntries(this.menuButtonEntries.entries);
    }
    get menuToggleClass() {
        return {
            ...super.menuToggleClass,
            o_menu_toggle_studio_app_creator_back:
                this.studio.MODES.APP_CREATOR === this.studio.mode,
        };
    }
}
