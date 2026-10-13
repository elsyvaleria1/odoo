/** @odoo-module native */
import { helpers } from "@odoo/o-spreadsheet";
import { OdooUIPlugin } from "@spreadsheet/plugins";

const { UNDO_REDO_PIVOT_COMMANDS } = helpers;
UNDO_REDO_PIVOT_COMMANDS.push("UPDATE_ODOO_PIVOT_DOMAIN");

export class PivotOdooUIPlugin extends OdooUIPlugin {
    static getters = /** @type {const} */ ([]);

    /** @param {Object} cmd */
    handle(cmd) {
        switch (cmd.type) {
            case "UPDATE_LOCALE":
            case "REFRESH_ALL_DATA_SOURCES":
                this.refreshAllPivots();
                break;
        }
    }

    refreshAllPivots() {
        for (const pivotId of this.getters.getPivotIds()) {
            this.dispatch("REFRESH_PIVOT", { id: pivotId });
        }
    }
}
