/** @odoo-module native */
import { patch } from "@web/core/utils/patch";
import { commandService } from "@web/ui/commands";

/**
 * Neutralize the commandPalette for portal users, as they can not have access
 * to some of its features (searching users, menus, ...)
 */
patch(commandService, {
    start(...args) {
        const commandService = super.start(...args);
        Object.assign(commandService, {
            openPalette() {},
            openMainPalette() {},
        });
        return commandService;
    },
});
