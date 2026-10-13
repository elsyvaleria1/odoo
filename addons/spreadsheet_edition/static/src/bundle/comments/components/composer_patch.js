/** @odoo-module native */
import { Composer } from "@mail/core/common/composer";
import { patch } from "@web/core/utils/patch";

patch(Composer.prototype, {
    get allowUpload() {
        return this._isSpreadsheetCellThread() ? false : super.allowUpload;
    },

    /** @private */
    _isSpreadsheetCellThread() {
        const threadModel = (this.thread ?? this.message?.thread)?.model;
        return threadModel === "spreadsheet.cell.thread";
    },
});
