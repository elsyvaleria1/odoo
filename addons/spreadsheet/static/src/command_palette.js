/** @odoo-module native */
import { components, Spreadsheet } from "@odoo/o-spreadsheet";
import { patch } from "@web/core/utils/patch";

import { useSpreadsheetCommandPalette } from "./command_provider.js";

const { Grid } = components;

patch(Spreadsheet.prototype, {
    setup() {
        super.setup();
        if (this.env.isDashboard()) {
            return;
        }
        useSpreadsheetCommandPalette();
    },
});

patch(Grid.prototype, {
    setup() {
        super.setup();
        delete this.keyDownMapping["Ctrl+K"];
    },
});
