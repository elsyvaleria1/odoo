/** @odoo-module native */
import { AbstractCellClipboardHandler, helpers } from "@odoo/o-spreadsheet";

const { isInside } = helpers;

export class CellThreadsClipboardHandler extends AbstractCellClipboardHandler {
    copy(data) {
        if (!data.zones.length) {
            return;
        }

        const zones = data.zones;
        const sheetId = this.getters.getActiveSheetId();
        const sheetThreads = this.getters.getSpreadsheetThreads([sheetId]);
        const threads = sheetThreads.filter((thread) =>
            isInside(thread.col, thread.row, zones[0]),
        );
        return { threads, zones };
    }

    paste(target, content, options) {
        if (!content.threads?.length || !target.zones.length) {
            return;
        }
        if (options?.isCutOperation && !options?.pasteOption) {
            const zones = target.zones;
            const sheetId = this.getters.getActiveSheetId();
            this.pasteFromCut(sheetId, zones, content);
        }
    }

    pasteFromCut(sheetId, target, content) {
        const cutZone = content.zones[0];

        const deltaCol = target[0].left - cutZone.left;
        const deltaRow = target[0].top - cutZone.top;
        for (const thread of content.threads) {
            this.dispatch("DELETE_COMMENT_THREAD", {
                sheetId: thread.sheetId,
                col: thread.col,
                row: thread.row,
                threadId: thread.threadId,
            });

            this.dispatch("ADD_COMMENT_THREAD", {
                sheetId,
                col: thread.col + deltaCol,
                row: thread.row + deltaRow,
                threadId: thread.threadId,
            });
        }
    }
}
