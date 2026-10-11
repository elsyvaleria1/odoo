/** @odoo-module native */
import { patch } from "@web/core/utils/patch";
import { commandService } from "@web/ui/commands";

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
